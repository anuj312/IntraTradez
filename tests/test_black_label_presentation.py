"""Guard Black Label's visual-only integration and preserved data hooks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf-8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf-8')
LAYER = (ROOT / 'black-label.css').read_text(encoding='utf-8')


def test_black_label_is_embedded_and_source_remains_editable():
    assert 'TREND HUNTER — BLACK LABEL' in LAYER
    assert CSS.endswith(LAYER)
    assert '<style id="pulse-spectra-premium">\n' + CSS.rstrip() + '\n</style>' in HTML


def test_title_and_market_status_hooks_stay_intact():
    assert '<h1 id="pageTitle">Trend Hunter</h1>' in HTML
    for tag in ('feedStatusText', 'feedChip', 'ticksChip', 'niftyRegimeCard', 'trackedValue'):
        assert f'id="{tag}"' in HTML
    assert '#pageTitle::after' in CSS
    assert '#pageTitle::before' in CSS


def test_mobile_no_sector_horizontal_scroll_and_stock_tables_still_scroll():
    assert 'grid-template-columns: repeat(14, minmax(0, 1fr)) !important' in CSS
    assert 'overflow-x: hidden !important; overflow-y: hidden !important;' in CSS
    assert '#sectorFlow .flow-list' in CSS
    assert 'overflow-y: auto !important' in CSS
    assert HTML.count('class="mobile-leader-switch"') == 3
