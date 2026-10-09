"""Ensure all six lists cap at ten while retaining six-row scrolling."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
CSS = (ROOT / "premium-terminal.css").read_text(encoding="utf-8")

def test_all_leaderboard_slices_share_ten_stock_limit():
    assert 'const LEADERBOARD_MAX_STOCKS = 10;' in HTML
    assert HTML.count('.slice(0, LEADERBOARD_MAX_STOCKS)') == 6
    assert 'LEADERBOARD_MAX_STOCKS = 15' not in HTML
    assert '${leaders.length} / 15' not in HTML
    assert '${declines.length} / 15' not in HTML
    for control in ['volumeLeadersCount','volumeDeclinesCount','changeLeadersCount','changeDeclinesCount']:
        assert re.search(r'id="' + control + r'">0 / 10</span>', HTML)

def test_six_row_viewport_and_scroll_retained():
    assert 'max-height: calc(40px + 6 * var(--th-stock-row-height))' in CSS
    assert 'overflow-y: auto !important' in CSS
    for element in ['gainersList','losersList','volumeLeadersList','volumeDeclinesList','changeLeadersList','changeDeclinesList']:
        assert re.search('id="' + element + r'"[^>]+scroll for positions 7 to 10', HTML)
    assert 'positions 8 to 15' not in HTML
    assert 'ONE-SCREEN WORKSPACE' in CSS

def test_premium_styles_sync():
    embedded=HTML.split('<style id="pulse-spectra-premium">',1)[1].split('</style>',1)[0]
    assert embedded.strip() == CSS.strip()
