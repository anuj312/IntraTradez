"""Razorpay sandbox is not a real lifetime entitlement."""
from pathlib import Path
from unittest.mock import patch
import hmac
import hashlib
import pytest
import member_payments as m

ROOT = Path(__file__).resolve().parents[1]
USER = {'id': '58b47bc1-44ee-450a-8cbd-c034c9daa42c', 'email': 'sandbox@example.com', 'full_name': 'Sandbox Trader'}


def env(*, key='rzp_test_12345', mode='google_test', allow_live=False):
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(m, 'MODE', mode))
    stack.enter_context(patch.object(m, 'ALLOW_LIVE_RAZORPAY', allow_live))
    stack.enter_context(patch.object(m, 'SUPABASE_URL', 'https://project.supabase.co'))
    stack.enter_context(patch.object(m, 'SUPABASE_ANON_KEY', 'anon'))
    stack.enter_context(patch.object(m, 'SUPABASE_SERVICE_ROLE_KEY', 'service'))
    stack.enter_context(patch.object(m, 'RAZORPAY_KEY_ID', key))
    stack.enter_context(patch.object(m, 'RAZORPAY_KEY_SECRET', 'test-secret'))
    return stack


def test_test_mode_config_is_paid_but_only_test():
    with env():
        payload = m.config_payload()
        assert m.enabled() and m.paid_mode() and m.test_mode() and not m.free_mode()
        assert payload['mode'] == 'google_test'
        assert payload['configured'] and payload['test_mode'] is True
        assert payload['real_payments_enabled'] is False
        assert payload['price_paise'] == 499900 and payload['currency'] == 'INR'
        assert payload['razorpay_key'].startswith('rzp_test_')


def test_live_key_never_used_by_test_mode_even_with_live_opt_in():
    with env(key='rzp_live_12345', allow_live=True):
        assert not m.configured()
        assert not m.config_payload()['razorpay_key']
        with pytest.raises(m.MembershipError) as error:
            m._razorpay('POST','orders',body={})
        assert error.value.code == 'payment_not_configured'


def test_real_checkout_cannot_be_armed_implicitly():
    with env(key='rzp_live_12345', mode='google', allow_live=False):
        assert not m.configured()
        with pytest.raises(m.MembershipError):
            m._razorpay('POST', 'orders', body={})
    with env(key='rzp_test_12345', mode='google', allow_live=True):
        assert not m.configured()


def test_test_tables_are_separate():
    with env():
        assert m._member_table() == 'th_test_memberships'
        assert m._order_table() == 'th_test_payment_orders'
    with env(mode='google', key='rzp_live_12345', allow_live=True):
        assert m._member_table() == 'th_memberships'
        assert m._order_table() == 'th_payment_orders'


def test_previously_blocked_google_account_cannot_be_activated_in_test_mode():
    calls=[]
    def db(method, table, **kw):
        calls.append(table)
        return [{'status':'blocked'}] if table == 'th_memberships' else []
    with env(), patch.object(m,'_db',side_effect=db):
        result = m.ensure_profile(USER)
        assert result['status'] == 'blocked'
        assert calls == ['th_test_memberships', 'th_memberships']


def test_order_uses_sandbox_provider_and_test_table():
    calls=[]
    def db(method, table, **kw):
        calls.append((method,table,kw.get('body')))
        return []
    order={'id':'order_abcdefghij','amount':499900,'currency':'INR'}
    with env(), patch.object(m, 'ensure_profile', return_value={'status':'pending'}), \
        patch.object(m,'_db',side_effect=db), patch.object(m,'_razorpay',return_value=order) as provider:
        result=m.create_order(USER)
        assert result['test_mode'] is True
        assert result['key'].startswith('rzp_test_')
        assert result['amount']==499900
        assert provider.call_args.args == ('POST','orders')
        assert calls[0][1] == 'th_test_payment_orders'
        assert calls[0][2]['amount_paise'] == 499900


def test_verified_test_capture_updates_only_test_tables():
    order={'order_id':'order_abcdefghij','user_id':USER['id'],'amount_paise':499900,'currency':'INR','status':'created','payment_id':None}
    payment={'id':'pay_abcdefghij','order_id':'order_abcdefghij','status':'captured','amount':499900,'currency':'INR'}
    writes=[]
    def db(method,table,**kw):
        if method=='PATCH': writes.append((table,kw.get('body')))
        return []
    with env(), patch.object(m,'_order_record',return_value=order), \
         patch.object(m,'_razorpay',return_value=payment), \
         patch.object(m,'get_profile',return_value={'status':'pending','paid_at':None}), \
         patch.object(m,'_db',side_effect=db):
        result=m._confirm_capture(order['order_id'],payment['id'],USER['id'])
        assert result == {'ok':True,'status':'active','test_mode':True}
    assert [name for name,_ in writes] == ['th_test_payment_orders','th_test_memberships']
    assert writes[1][1]['status'] == 'active'


def test_pending_test_user_cannot_access_stock_data():
    with env(), patch.object(m,'member_status',return_value=(USER,{'status':'pending','paid_at':None})):
        m.invalidate_cache()
        assert not m.has_paid_access('long_fake_bearer_token_test_mode')
        m.invalidate_cache()


def test_paid_test_user_can_access_and_real_mode_cannot_use_same_status():
    with env(), patch.object(m,'member_status',return_value=(USER,{'status':'active','paid_at':'2026-10-10T00:00:00Z'})):
        m.invalidate_cache()
        assert m.has_paid_access('long_fake_bearer_token_paid_test')
        m.invalidate_cache()
    with env(mode='google', key='rzp_live_12345', allow_live=False):
        assert not m.has_paid_access('long_fake_bearer_token_paid_test')


def test_ui_explicitly_labels_test_checkout_and_keeps_live_member_separate():
    html=(ROOT/'intraday-momentum-scanner.html').read_text()
    assert "config.mode === 'google_test'" in html
    assert 'TEST MODE · NO REAL CHARGE' in html
    assert 'TEST MEMBER · DEMO ONLY' in html
    assert "String(order.key || '').startsWith('rzp_test_')" in html
    assert 'Try ₹4,999 Test Checkout' in html
    assert 'SUPABASE_RAZORPAY_TEST_SETUP.sql' in (ROOT/'MDS/RAZORPAY_TEST_MODE_SETUP.md').read_text()
