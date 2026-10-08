"""Static visual-skin regression checks; no browser/network required."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_skin_embedded_and_synced():
    html = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
    css = (ROOT / "premium-terminal.css").read_text(encoding="utf-8").strip()
    begin = '<style id="pulse-spectra-premium">\n'
    assert html.count(begin) == 1
    assert html.split(begin, 1)[1].split('</style>', 1)[0].strip() == css
    assert 'family=Space+Grotesk' in html
    assert 'SPECTRA // SIGNAL ENGINE' in html


def test_original_interactions_and_login_unaffected():
    html = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
    assert 'id="themeToggle"' in html
    assert 'initializeTheme()' in html
    assert 'id="sectorModal"' in html
    assert 'data-chart-symbol' not in html  # removed as requested
    assert '/api/access/login' in html
    assert '/api/access/request-otp' not in html
    assert '/api/access/verify-otp' not in html
    assert (ROOT / 'numbers.txt').exists()
    assert 'rootDir: outputs' in (ROOT / 'render.yaml').read_text()


def test_skin_accessibility_and_layout():
    css = (ROOT / 'premium-terminal.css').read_text()
    assert '@media (prefers-reduced-motion: reduce)' in css
    assert '@media (max-width: 760px)' in css
    assert '.sector-modal' in css
    assert '.flow-fill.positive' in css
    assert '.flow-fill.negative' in css
