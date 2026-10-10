"""Guard the premium Google-first lifetime-card experience against regressions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'intraday-momentum-scanner.html'
CSS = ROOT / 'membership-elite-card.css'

def test_google_login_is_first_and_plan_is_second():
    src = HTML.read_text(encoding='utf-8')
    assert '<section class="google-stage-login" aria-label="Step 1: Google sign-in">' in src
    assert '<section class="google-stage-plan" hidden aria-label="Step 2: Lifetime membership">' in src
    assert "if (login) login.hidden = signedIn;" in src
    assert "if (plan) plan.hidden = !signedIn || active || googleFreeMode;" in src
    assert "if (pay) pay.hidden = !signedIn || active || status === 'blocked' || googleFreeMode;" in src
    assert 'Your membership options appear after sign-in.' in src


def test_membership_card_only_uses_auth_confirmed_member_identity():
    src = HTML.read_text(encoding='utf-8')
    assert 'luxe-metal-card' in src
    assert 'luxe-card-name' in src
    assert 'element.textContent = displayName' in src
    assert 'CARD HOLDER' in src
    assert 'LIFETIME<br>ACCESS' in src
    assert "membershipApi('/api/verify-payment'" in src
    assert "status === 'active'" in src
    assert 'googleMemberSignOut' in src


def test_rzp_demo_stays_test_only_and_source_contains_no_secrets():
    src = HTML.read_text(encoding='utf-8')
    assert 'TEST MODE · NO REAL CHARGE' in src
    assert 'Try ₹4,999 Test Checkout' in src
    assert 'No real money deducted' in src
    assert "String(order.key || '').startsWith('rzp_test_')" in src
    assert 'RAZORPAY_KEY_SECRET=' not in src
    assert 'SUPABASE_SERVICE_ROLE_KEY=' not in src


def test_css_is_embedded_and_mobile_safe():
    css = CSS.read_text(encoding='utf-8')
    html = HTML.read_text(encoding='utf-8')
    premium = (ROOT/'premium-terminal.css').read_text(encoding='utf-8')
    # The standalone source was synced in two append-only passes to preserve
    # the baseline CSS; verify both fragments are present in the embedded CSS.
    initial, compact = css.split('/* Tighter payment presentation on standard laptop desktops:', 1)
    assert initial.strip() in premium
    assert '/* Tighter payment presentation on standard laptop desktops:' + compact in premium
    assert premium.rstrip() in html
    assert '@media (max-width:760px)' in css
    assert '@media (min-width:761px) and (max-height:960px)' in css
    assert 'overflow-y: auto !important' in css
    assert 'google-stage-plan' in css
