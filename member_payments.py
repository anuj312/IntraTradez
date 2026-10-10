"""Google (Supabase Auth) and Razorpay lifetime membership for Trend Hunter.

Trust boundaries: OAuth token is checked with Supabase Auth; Supabase service-role
key and Razorpay secret never reach the browser. Payment is NOT activated on a
Checkout callback alone: server validates HMAC, fetches the captured payment,
checks INR/amount/order/user, then persists the entitlement in Supabase.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
import time
import uuid
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from urllib.parse import quote

import requests

# Local development uses outputs/.env; real Render secrets stay in Environment.
# override=False ensures Render-injected environment variables always take priority.
load_dotenv(Path(__file__).resolve().parent / '.env', override=False)

log = logging.getLogger('trendhunter.membership')
PRICE_PAISE = 499900
CURRENCY = 'INR'
MODE = os.getenv('MEMBERSHIP_AUTH_MODE', 'phone').strip().lower()
SUPABASE_URL = os.getenv('SUPABASE_URL', '').strip().rstrip('/')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', '').strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
RAZORPAY_KEY_ID = os.getenv('RAZORPAY_KEY_ID', '').strip()
RAZORPAY_KEY_SECRET = os.getenv('RAZORPAY_KEY_SECRET', '').strip()
RAZORPAY_WEBHOOK_SECRET = os.getenv('RAZORPAY_WEBHOOK_SECRET', '').strip()
# This release is strictly test-only: even if production keys/flags are
# mistakenly supplied, live charging stays disabled in this codebase.
ALLOW_LIVE_RAZORPAY = False

if SUPABASE_URL and not re.fullmatch(r'https://[a-zA-Z0-9.-]+\.supabase\.co', SUPABASE_URL):
    raise ValueError('SUPABASE_URL must be an HTTPS *.supabase.co project URL')

_cache: dict[str, tuple[float, dict[str, Any], bool]] = {}
_cache_lock = threading.Lock()

class MembershipError(Exception):
    def __init__(self, code='membership_unavailable', status=503):
        super().__init__(code)
        self.code = code
        self.status = status


def enabled():
    # Both variants enforce Supabase-verified Google identity on every protected API.
    return MODE in ('google', 'google_free', 'google_test')


def free_mode():
    return MODE == 'google_free'


def test_mode():
    return MODE == 'google_test'


def _member_table():
    return 'th_test_memberships' if test_mode() else 'th_memberships'


def _order_table():
    return 'th_test_payment_orders' if test_mode() else 'th_payment_orders'


def paid_mode():
    return MODE in ('google', 'google_test')


def _valid_razorpay_keys():
    if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        return False
    if test_mode():
        return RAZORPAY_KEY_ID.startswith('rzp_test_')
    # Production Razorpay checkout is intentionally DISABLED in this build.
    return False


def configured():
    auth_ready = all([SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY])
    return auth_ready and (free_mode() or _valid_razorpay_keys())


def config_payload():
    return {'mode': MODE if enabled() else 'phone',
            'configured': configured() if enabled() else True,
            'supabase_url': SUPABASE_URL if enabled() else '',
            'supabase_anon_key': SUPABASE_ANON_KEY if enabled() else '',
            'razorpay_key': RAZORPAY_KEY_ID if paid_mode() and configured() else '',
            'price_paise': PRICE_PAISE if paid_mode() else 0, 'currency': CURRENCY,
            'test_mode': test_mode(), 'real_payments_enabled': MODE == 'google' and _valid_razorpay_keys()}


def bearer_token():
    from flask import request
    header = request.headers.get('Authorization', '')
    match = re.fullmatch(r'Bearer\s+([A-Za-z0-9._-]{20,8192})', header)
    return match.group(1) if match else None


def _call(method, url, *, headers=None, auth=None, json=None, provider='supabase'):
    try:
        resp = requests.request(method, url, headers=headers, auth=auth, json=json, timeout=10)
    except requests.RequestException as exc:
        log.warning('Membership service unavailable: %s', type(exc).__name__)
        if provider == 'razorpay':
            raise MembershipError('razorpay_api_error', 500) from exc
        raise MembershipError() from exc
    if not 200 <= resp.status_code < 300:
        log.warning('Membership upstream %s HTTP %s', method, resp.status_code)
        if resp.status_code in (401, 403):
            raise MembershipError('unauthorized', 401)
        if provider == 'razorpay':
            raise MembershipError('razorpay_api_error', 500)
        raise MembershipError('membership_unavailable', 503)
    try:
        return resp.json()
    except ValueError as exc:
        if provider == 'razorpay':
            raise MembershipError('razorpay_api_error', 500) from exc
        raise MembershipError() from exc


def _admin_headers():
    return {'apikey': SUPABASE_SERVICE_ROLE_KEY,
            'Authorization': 'Bearer ' + SUPABASE_SERVICE_ROLE_KEY,
            'Content-Type': 'application/json', 'Prefer': 'return=representation'}


def _db(method, table, *, query='', body=None, extra_headers=None):
    headers = _admin_headers()
    if extra_headers:
        headers.update(extra_headers)
    return _call(method, SUPABASE_URL + '/rest/v1/' + table + query, headers=headers, json=body)


def get_google_user(token):
    if not token:
        raise MembershipError('google_login_required', 401)
    user = _call('GET', SUPABASE_URL + '/auth/v1/user',
                 headers={'apikey': SUPABASE_ANON_KEY, 'Authorization': 'Bearer ' + token})
    if not user.get('id') or not user.get('email') or not user.get('email_confirmed_at'):
        raise MembershipError('google_login_required', 401)
    # Do not permit other Supabase login providers to act as a Google account.
    providers = set(user.get('app_metadata', {}).get('providers') or [])
    if user.get('app_metadata', {}).get('provider'):
        providers.add(user['app_metadata']['provider'])
    if 'google' not in providers:
        raise MembershipError('google_login_required', 401)
    return {'id': str(user['id']), 'email': str(user['email']).lower(),
            'full_name': str(user.get('user_metadata', {}).get('full_name') or
                             user.get('user_metadata', {}).get('name') or
                             user.get('email').split('@')[0])[:120]}


def get_profile(user_id):
    rows = _db('GET', _member_table(), query='?user_id=eq.' + quote(user_id, safe='') +
               '&select=user_id,email,full_name,status,paid_at')
    profile = rows[0] if rows else None
    if test_mode():
        # A previously blocked Google user must remain blocked in the demo flow.
        master = _db('GET', 'th_memberships', query='?user_id=eq.' + quote(user_id, safe='') +
                     '&select=status')
        if master and master[0].get('status') == 'blocked':
            return {**(profile or {'user_id': user_id, 'paid_at': None}), 'status': 'blocked'}
    return profile


def ensure_profile(user):
    profile = get_profile(user['id'])
    if profile:
        # Preserve stored membership status and payment fields on return visits.
        return profile
    rows = _db('POST', _member_table(), body={
        'user_id': user['id'], 'email': user['email'],
        'full_name': user['full_name'], 'status': 'pending',
    }, extra_headers={'Prefer': 'resolution=ignore-duplicates,return=representation'})
    return rows[0] if rows else get_profile(user['id'])


def member_status(token):
    if not configured():
        raise MembershipError('membership_not_configured', 503)
    user = get_google_user(token)
    profile = ensure_profile(user)
    return user, profile


def has_paid_access(token):
    if not enabled() or not configured() or not token:
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(digest)
        if hit and hit[0] > now:
            return hit[2]
    user, profile = member_status(token)
    paid = bool(profile and (profile.get('status') != 'blocked' if free_mode()
                            else profile.get('status') == 'active' and profile.get('paid_at')))
    with _cache_lock:
        if len(_cache) >= 2048:
            _cache.clear()
        _cache[digest] = (now + 30, user, paid)
    return paid


def invalidate_cache():
    with _cache_lock:
        _cache.clear()


def _razorpay(method, path, *, body=None):
    if not _valid_razorpay_keys():
        raise MembershipError('payment_not_configured', 503)
    return _call(method, 'https://api.razorpay.com/v1/' + path,
                 auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), json=body, provider='razorpay')


def validate_order_request(payload):
    """A membership order ALWAYS costs ₹4,999; never trust browser pricing.

    The optional amount/currency fields are accepted for the documented generic
    Checkout API, but must exactly match this server-side product price.
    Receipt is generated by the server, not accepted from the client.
    """
    if not isinstance(payload, dict):
        raise MembershipError('invalid_order_request', 400)
    if 'amount' in payload:
        amount = payload['amount']
        if type(amount) is not int or amount < 100 or amount != PRICE_PAISE:
            raise MembershipError('invalid_amount', 400)
    if 'currency' in payload and payload['currency'] != CURRENCY:
        raise MembershipError('invalid_currency', 400)
    if 'receipt' in payload and payload['receipt'] is not None:
        # The server always issues its own unique receipt ID.
        raise MembershipError('receipt_is_server_generated', 400)


def create_order(user):
    if not configured():
        raise MembershipError('payment_not_configured', 503)
    profile = ensure_profile(user)
    if profile and profile['status'] == 'active':
        raise MembershipError('already_member', 409)
    if profile and profile['status'] == 'blocked':
        raise MembershipError('membership_blocked', 403)
    receipt = 'th-' + uuid.uuid4().hex[:26]
    order = _razorpay('POST', 'orders', body={'amount': PRICE_PAISE, 'currency': CURRENCY,
        'receipt': receipt, 'notes': {'purpose': 'Trend Hunter Lifetime', 'user_id': user['id']}})
    if not order.get('id') or order.get('amount') != PRICE_PAISE or order.get('currency') != CURRENCY:
        raise MembershipError('invalid_payment_order', 502)
    _db('POST', _order_table(), body={'order_id': order['id'], 'user_id': user['id'],
        'amount_paise': PRICE_PAISE, 'currency': CURRENCY, 'status': 'created'})
    return {'order_id': order['id'], 'key': RAZORPAY_KEY_ID, 'amount': PRICE_PAISE,
            'currency': CURRENCY, 'name': user['full_name'], 'email': user['email'],
            'test_mode': test_mode()}


def _order_record(order_id):
    rows = _db('GET', _order_table(), query='?order_id=eq.' + quote(order_id, safe='') +
               '&select=order_id,user_id,amount_paise,currency,status,payment_id')
    return rows[0] if rows else None


def _confirm_capture(order_id, payment_id, expected_user_id=None):
    order = _order_record(order_id)
    if not order or (expected_user_id and order['user_id'] != expected_user_id):
        raise MembershipError('payment_order_not_owned', 403)
    if order['amount_paise'] != PRICE_PAISE or order['currency'] != CURRENCY:
        raise MembershipError('payment_amount_mismatch', 403)
    if order.get('payment_id') and order['payment_id'] != payment_id:
        raise MembershipError('order_already_paid', 409)
    payment = _razorpay('GET', 'payments/' + quote(payment_id, safe=''))
    if (payment.get('id') != payment_id or payment.get('order_id') != order_id or
        payment.get('status') != 'captured' or payment.get('amount') != PRICE_PAISE or
        payment.get('currency') != CURRENCY):
        raise MembershipError('payment_not_captured', 409)
    profile = get_profile(order['user_id'])
    if not profile or profile['status'] == 'blocked':
        raise MembershipError('membership_blocked', 403)
    # Orders are unique and payment_id has a DB unique constraint. Duplicate webhooks
    # and frontend retries remain idempotent.
    _db('PATCH', _order_table(), query='?order_id=eq.' + quote(order_id, safe=''),
        body={'status': 'paid', 'payment_id': payment_id})
    _db('PATCH', _member_table(), query='?user_id=eq.' + quote(order['user_id'], safe=''),
        body={'status': 'active', 'paid_at': profile.get('paid_at') or datetime.now(timezone.utc).isoformat()})
    invalidate_cache()
    return {'ok': True, 'status': 'active', 'test_mode': test_mode()}


def verify_checkout(user, payload):
    if not isinstance(payload, dict):
        raise MembershipError('invalid_payment_request', 400)
    if not _valid_razorpay_keys():
        raise MembershipError('payment_not_configured', 503)
    order_id = str(payload.get('razorpay_order_id') or '')
    payment_id = str(payload.get('razorpay_payment_id') or '')
    signature = str(payload.get('razorpay_signature') or '')
    if not all((order_id, payment_id, signature)):
        raise MembershipError('missing_payment_fields', 400)
    if not re.fullmatch(r'order_[A-Za-z0-9]{5,70}', order_id) or not re.fullmatch(r'pay_[A-Za-z0-9]{5,70}', payment_id) or not re.fullmatch(r'[a-fA-F0-9]{64}', signature):
        raise MembershipError('invalid_payment_signature', 400)
    expected = hmac.new(RAZORPAY_KEY_SECRET.encode(), (order_id + '|' + payment_id).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise MembershipError('invalid_payment_signature', 400)
    return _confirm_capture(order_id, payment_id, user['id'])


def handle_webhook(body, signature):
    if not _valid_razorpay_keys():
        raise MembershipError('payment_not_configured', 503)
    if not RAZORPAY_WEBHOOK_SECRET:
        raise MembershipError('webhook_not_configured', 503)
    expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise MembershipError('invalid_webhook_signature', 403)
    try:
        import json
        event = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise MembershipError('invalid_webhook_payload', 400) from exc
    if event.get('event') == 'payment.captured':
        payment = (event.get('payload', {}).get('payment', {}).get('entity') or {})
        if payment.get('id') and payment.get('order_id'):
            _confirm_capture(str(payment['order_id']), str(payment['id']))
    return {'ok': True}
