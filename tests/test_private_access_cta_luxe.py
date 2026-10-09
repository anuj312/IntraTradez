"""Private access CTA styling must preserve approved-number authentication."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf-8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf-8')
OVERLAY = (ROOT / 'private-access-cta-luxe.css').read_text(encoding='utf-8')


def test_premium_private_access_cta_is_embedded_after_black_label():
    assert OVERLAY.strip() in CSS
    assert '<style id="pulse-spectra-premium">\n' + CSS.rstrip() + '\n</style>' in HTML
    assert '.member-gated .gate-join-link:focus-visible' in CSS
    assert '@media (prefers-reduced-motion: reduce)' in OVERLAY


def test_access_group_urls_and_forms_are_preserved():
    assert HTML.count('Join private access group') == 4
    assert HTML.count('https://cosmofeed.com/vig/6a250fb87399a000136dec6b') == 4
    assert HTML.count('class="access-form access-gate-form"') == 4
    assert HTML.count('class="gate-footnote"') == 4
