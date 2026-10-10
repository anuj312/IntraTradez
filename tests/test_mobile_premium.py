"""Static guardrails for phone/tablet layout; dynamic layout checked with Chromium."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf-8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf-8')


def test_3_independent_phone_switches():
    assert HTML.count('class="mobile-leader-switch"') == 3
    assert HTML.count(' data-mobile-side-active="gainers">') == 3
    assert "grid.dataset.mobileSideActive = button.dataset.mobileSide" in HTML


def test_phone_table_filters_are_discoverable():
    assert 'id="mobileFilterToggle"' in HTML
    assert 'aria-expanded="false"' in HTML
    assert '.toolbar.mobile-filters-open .select-wrap' in CSS


def test_phone_keeps_table_scrolling_and_sector_bars_fit_one_screen():
    assert '.leaders-side .leader-list, #volumeRatioView .leader-list, #changeView .leader-list' in CSS
    assert 'touch-action: pan-y' in CSS
    assert 'grid-template-columns: repeat(var(--th-sector-count, 15), minmax(0, 1fr)) !important' in CSS
    assert '#sectorFlow .flow-list' in CSS
    assert 'overflow-x: hidden !important; overflow-y: hidden !important;' in CSS


def test_mobile_only_changes_preserve_desktop_styles():
    assert '@media (max-width: 900px)' in CSS
    assert '.mobile-leader-switch, .mobile-filter-toggle { display:none; }' in CSS
    assert 'aria-label="Log out"' in HTML
