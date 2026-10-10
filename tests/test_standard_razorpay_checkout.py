"""Standard Checkout aliases + fixed-amount sandbox payment protections."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import hmac
import pytest
import member_payments as m


def test_validate_amount_and_currency_and_server_receipt():
    m.validate_order_request({})
    m.validate_order_request({'amount': 499900, 'currency': 'INR'})
    for bad in (99, 100, 999, '499900', None, True, -1, 499901):
        with pytest.raises(m.MembershipError) as error:
            m.validate_order_request({'amount': bad})
        assert error.value.status == 400
    with pytest.raises(m.MembershipError) as error:
        m.validate_order_request({'currency': 'USD'})
    assert error.value.status == 400
    with pytest.raises(m.MembershipError) as error:
        m.validate_order_request({'receipt': 'client-receipt'})
    assert error.value.status == 400
    with pytest.raises(m.MembershipError) as error:
        m.validate_order_request(['not', 'a', 'dict'])
    assert error.value.status == 400


def test_checkout_missing_fields_or_wrong_signature_rejected_without_db_access():
    with patch.object(m, '_valid_razorpay_keys', return_value=True), \
         patch.object(m, 'RAZORPAY_KEY_SECRET', 'dummy-secret'), \
         patch.object(m, '_order_record') as lookup:
        with pytest.raises(m.MembershipError) as error:
            m.verify_checkout({'id': '123'}, {'razorpay_order_id': 'order_abcdef'})
        assert error.value.code == 'missing_payment_fields'
        assert error.value.status == 400
        with pytest.raises(m.MembershipError) as error:
            m.verify_checkout({'id': '123'}, ['bad'])
        assert error.value.status == 400
        with pytest.raises(m.MembershipError) as error:
            m.verify_checkout({'id': '123'}, {
                'razorpay_order_id': 'order_abcdef', 'razorpay_payment_id': 'pay_abcdef',
                'razorpay_signature': '0' * 64})
        assert error.value.status == 400
        lookup.assert_not_called()


def test_upstream_razorpay_errors_are_safe_and_correct_codes():
    for code, expected in ((401, 401), (403, 401), (429, 500), (500, 500)):
        fake = SimpleNamespace(status_code=code)
        with patch.object(m.requests, 'request', return_value=fake):
            with pytest.raises(m.MembershipError) as error:
                m._call('POST', 'https://api.razorpay.com/v1/orders', provider='razorpay')
            assert error.value.status == expected


def test_live_keys_not_exposed_in_google_test_mode():
    with patch.object(m, 'MODE', 'google_test'), \
         patch.object(m, 'RAZORPAY_KEY_ID', 'rzp_live_dummy'), \
         patch.object(m, 'RAZORPAY_KEY_SECRET', 'dummy-secret'):
        assert not m._valid_razorpay_keys()
        assert m.config_payload()['razorpay_key'] == ''


def test_alias_endpoints_and_frontend_checkout_present():
    src = (Path(__file__).parents[1] / 'live_scanner_server.py').read_text()
    html = (Path(__file__).parents[1] / 'intraday-momentum-scanner.html').read_text()
    for path in ('/api/create-order','/api/verify-payment','/api/membership/order','/api/membership/verify'):
        assert path in src
    assert 'https://checkout.razorpay.com/v1/checkout.js' in html
    assert "membershipApi('/api/create-order'" in html
    assert "membershipApi('/api/verify-payment'" in html
    assert "checkout.on('payment.failed'" in html
    assert 'ondismiss:' in html
    assert 'RAZORPAY_KEY_SECRET' not in html


def test_ignored_env_and_local_env_loading():
    root = Path(__file__).parents[1]
    assert '.env' in (root / '.gitignore').read_text().splitlines()
    assert 'load_dotenv(' in (root / 'member_payments.py').read_text()
    assert 'RAZORPAY_KEY_SECRET=' in (root / '.env.example').read_text()


def test_new_flask_handlers_use_existing_payment_logic():
    """Exercise route handlers isolated from Kite/Flask network requirements."""
    import ast
    from types import SimpleNamespace
    backend = (Path(__file__).parents[1] / 'live_scanner_server.py').read_text()
    tree = ast.parse(backend)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('membership_order', 'membership_verify')]
    assert len(nodes) == 2
    class FakeApp:
        def post(self, name): return lambda function: function
    class Reply(dict):
        def __init__(self, d): super().__init__(d); self.headers = {}
    payload = {'amount': 499900, 'currency': 'INR'}
    env = {
        'app': FakeApp(),
        'jsonify': lambda value: Reply(value),
        'request': SimpleNamespace(get_json=lambda silent=True: payload),
        'membership': SimpleNamespace(paid_mode=lambda: True,
            get_google_user=lambda token: {'id':'fake'}, bearer_token=lambda:'fake-token',
            validate_order_request=m.validate_order_request,
            create_order=lambda user:{'order_id':'order_abcdefghij','amount':499900,'currency':'INR'},
            verify_checkout=lambda user,payload:{'ok': True}, MembershipError=m.MembershipError)
    }
    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<isolated routes>', 'exec'), env)
    created = env['membership_order']()
    assert created['order_id'] == 'order_abcdefghij'
    assert created.headers['Cache-Control'] == 'no-store'
    payload['amount'] = 99
    denied, status = env['membership_order']()
    assert status == 400 and denied['error'] == 'invalid_amount'
    verified = env['membership_verify']()
    assert verified['ok'] is True
    assert verified.headers['Cache-Control'] == 'no-store'


def test_live_payment_never_activates_in_this_sandbox_release():
    with patch.object(m, 'MODE','google'), \
         patch.object(m, 'RAZORPAY_KEY_ID','rzp_live_abcdef'), \
         patch.object(m, 'RAZORPAY_KEY_SECRET','dummy-secret'):
        assert m._valid_razorpay_keys() is False
        assert m.config_payload()['real_payments_enabled'] is False
