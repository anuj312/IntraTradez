"""Security regression tests for Google lifetime membership and Razorpay."""
import hashlib
import hmac
import importlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import member_payments as m


def good_user():
    return {'id': '690857ad-784f-4357-9662-5d40fc08cb9d', 'email': 'trader@example.com', 'full_name': 'Example Trader'}


def good_order():
    return {'order_id': 'order_abcdefghij', 'user_id': good_user()['id'], 'amount_paise': 499900,
            'currency': 'INR', 'status': 'created', 'payment_id': None}


def good_payment(status='captured', amount=499900):
    return {'id': 'pay_abcdefghij', 'order_id': 'order_abcdefghij',
            'currency': 'INR', 'status': status, 'amount': amount}


def checkout_signature():
    return hmac.new(b'test-rzp-secret', b'order_abcdefghij|pay_abcdefghij', hashlib.sha256).hexdigest()


def test_price_is_exactly_4999_rupees():
    assert m.PRICE_PAISE == 499900
    assert m.CURRENCY == 'INR'


def test_valid_capture_activates_member():
    changes = []
    def mock_db(method, table, *, query='', body=None, extra_headers=None):
        if method == 'PATCH': changes.append((table, body))
        return []
    with patch.object(m, 'MODE', 'google'), \
             patch.object(m, 'RAZORPAY_KEY_SECRET', 'test-rzp-secret'), \
             patch.object(m, '_valid_razorpay_keys', return_value=True), \
         patch.object(m, '_order_record', return_value=good_order()), \
         patch.object(m, '_razorpay', return_value=good_payment()), \
         patch.object(m, 'get_profile', return_value={'status':'pending','paid_at':None}), \
         patch.object(m, '_db', side_effect=mock_db):
        assert m.verify_checkout(good_user(), {'razorpay_order_id':'order_abcdefghij',
              'razorpay_payment_id':'pay_abcdefghij','razorpay_signature':checkout_signature()})['status'] == 'active'
        assert ('th_payment_orders', {'status':'paid','payment_id':'pay_abcdefghij'}) in changes
        assert [item for item in changes if item[0] == 'th_memberships'][0][1]['status'] == 'active'


def test_bad_signature_is_rejected_before_db_or_provider_lookup():
    with patch.object(m, 'RAZORPAY_KEY_SECRET', 'test-rzp-secret'), \
             patch.object(m, '_valid_razorpay_keys', return_value=True), \
         patch.object(m, '_order_record') as lookup:
        with pytest.raises(m.MembershipError) as err:
            m.verify_checkout(good_user(), {'razorpay_order_id':'order_abcdefghij',
                'razorpay_payment_id':'pay_abcdefghij','razorpay_signature':'0'*64})
        assert err.value.code == 'invalid_payment_signature'
        lookup.assert_not_called()


@pytest.mark.parametrize('status,amount', [('authorized',499900),('created',499900),('captured',490000)])
def test_uncaptured_or_wrong_amount_cannot_activate(status,amount):
    with patch.object(m, '_order_record', return_value=good_order()), \
         patch.object(m, '_razorpay', return_value=good_payment(status,amount)), \
         patch.object(m, '_db') as update:
        with pytest.raises(m.MembershipError) as err:
            m._confirm_capture('order_abcdefghij','pay_abcdefghij',good_user()['id'])
        assert err.value.code == 'payment_not_captured'
        update.assert_not_called()


def test_wrong_user_cannot_claim_order():
    with patch.object(m, '_order_record', return_value=good_order()), patch.object(m, '_razorpay') as razorpay:
        with pytest.raises(m.MembershipError) as err:
            m._confirm_capture('order_abcdefghij', 'pay_abcdefghij', 'someone_else')
        assert err.value.code == 'payment_order_not_owned'
        razorpay.assert_not_called()


def test_blocked_user_never_activated():
    with patch.object(m, '_order_record', return_value=good_order()), \
         patch.object(m, '_razorpay', return_value=good_payment()), \
         patch.object(m, 'get_profile', return_value={'status':'blocked'}), \
         patch.object(m, '_db') as db:
        with pytest.raises(m.MembershipError) as err:
            m._confirm_capture('order_abcdefghij', 'pay_abcdefghij', good_user()['id'])
        assert err.value.code == 'membership_blocked'
        db.assert_not_called()


def test_webhook_signature_must_match_raw_body():
    body=b'{"event":"payment.captured","payload":{}}'
    with patch.object(m, 'RAZORPAY_WEBHOOK_SECRET', 'secret'), patch.object(m, '_valid_razorpay_keys', return_value=True):
        with pytest.raises(m.MembershipError) as err:
            m.handle_webhook(body, '00'*32)
        assert err.value.code == 'invalid_webhook_signature'
        valid=hmac.new(b'secret', body, hashlib.sha256).hexdigest()
        assert m.handle_webhook(body,valid)['ok']


def test_google_membership_always_rejects_missing_token():
    with patch.object(m, 'MODE','google'), patch.object(m, 'configured', return_value=True):
        assert not m.has_paid_access(None)


def test_google_provider_required():
    data={'id':'uuid','email':'notgoogle@example.com', 'email_confirmed_at':'2026-10-01',
          'app_metadata':{'provider':'email','providers':['email']}}
    with patch.object(m, '_call',return_value=data):
        with pytest.raises(m.MembershipError) as err:
            m.get_google_user('valid_token_with_20_chars')
        assert err.value.code == 'google_login_required'


def test_premium_html_has_required_checkout_and_member_name_logic():
    from pathlib import Path
    html=(Path(__file__).parents[1] / 'intraday-momentum-scanner.html').read_text()
    backend=(Path(__file__).parents[1] / 'live_scanner_server.py').read_text()
    for phrase in ('Continue with Google','Lifetime Access','₹4,999','/api/verify-payment',
                   'LIFETIME PRO MEMBER','googleMembershipMode','membershipHeaders()'):
        assert phrase in html
    assert 'membership.has_paid_access(membership.bearer_token())' in backend
    assert 'if membership.enabled():' in backend
