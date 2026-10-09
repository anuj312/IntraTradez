"""Navigation/branding safety checks for premium command deck sidebar."""
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf-8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf-8')


def test_navigation_routes_retained():
    assert HTML.count('data-scroll="sectorFlow"') == 1
    assert HTML.count('data-view="volumeRatio"') == 1
    assert HTML.count('data-view="change"') == 1
    assert '<span class="nav-title">Momentum Radar</span>' in HTML
    assert 'document.querySelectorAll(".nav button")' in HTML


def test_redesigned_sidebar_has_all_content():
    assert '<div class="brand-name">Trend Hunter</div>' in HTML
    assert 'SPECTRA // SIGNAL ENGINE' in HTML
    assert HTML.count('class="nav-overline"') == 4
    assert HTML.count('class="nav-arrow"') == 4
    assert 'Research mode' in HTML
    assert 'Desk view' in HTML
    assert 'nav-icon' in HTML


def test_sidebar_style_is_desktop_only_and_mobile_uses_compact_bar():
    assert 'OBSIDIAN COMMAND DECK' in CSS
    assert '@media (min-width:901px)' in CSS
    assert '@media (max-width:900px)' in CSS
    assert 'rail-ambient,.rail-section-count,.brand-kicker' in CSS
    assert 'grid-template-columns: repeat(14, minmax(0, 1fr)) !important' in CSS
