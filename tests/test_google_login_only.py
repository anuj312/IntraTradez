"""Google-only mode: no payment credentials, no checkout, no anonymous stock access."""
from unittest.mock import patch
import member_payments as m


def test_google_only_config_requires_supabase_but_not_razorpay():
    with patch.object(m, 'MODE','google_free'), patch.object(m, 'SUPABASE_URL','https://project.supabase.co'), \
         patch.object(m,'SUPABASE_ANON_KEY','anon-jwt'), patch.object(m,'SUPABASE_SERVICE_ROLE_KEY','service-jwt'), \
         patch.object(m,'RAZORPAY_KEY_ID',''), patch.object(m,'RAZORPAY_KEY_SECRET',''):
        assert m.enabled() and m.free_mode() and not m.paid_mode()
        assert m.configured()
        payload=m.config_payload()
        assert payload['mode']=='google_free'
        assert payload['price_paise']==0
        assert payload['razorpay_key']==''


def test_google_only_denies_anonymous_and_blocked_users():
    with patch.object(m, 'MODE','google_free'), patch.object(m,'configured',return_value=True), \
         patch.object(m, 'member_status',return_value=({'id':'somebody'}, {'status':'blocked'})):
        m.invalidate_cache()
        assert not m.has_paid_access(None)
        assert not m.has_paid_access('valid_google_token_for_blocked_member')
        m.invalidate_cache()


def test_google_only_allows_signed_in_pending_user_but_paid_mode_does_not():
    person=({'id':'somebody'}, {'status':'pending','paid_at':None})
    with patch.object(m, 'MODE','google_free'), patch.object(m,'configured',return_value=True), \
         patch.object(m,'member_status',return_value=person):
        m.invalidate_cache()
        assert m.has_paid_access('free_signed_in_google_access_token')
        m.invalidate_cache()
    with patch.object(m, 'MODE','google'), patch.object(m,'configured',return_value=True), \
         patch.object(m,'member_status',return_value=person):
        assert not m.has_paid_access('free_signed_in_google_access_token')
        m.invalidate_cache()


def test_google_only_has_no_checkout_in_mode():
    from pathlib import Path
    html=(Path(__file__).parents[1]/'intraday-momentum-scanner.html').read_text()
    backend=(Path(__file__).parents[1]/'live_scanner_server.py').read_text()
    assert "config.mode === 'google_free'" in html
    assert "googleFreeMode" in html
    assert "if not membership.paid_mode():" in backend
    assert "google_login_only" in backend
    assert 'SUPABASE_GOOGLE_ONLY_SETUP.sql' not in html
