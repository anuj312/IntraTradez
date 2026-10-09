"""Regression guards for six-row stock lists and elastic sector flow visuals."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "premium-terminal.css").read_text(encoding="utf-8")
HTML = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
CUSTOM = CSS.split("/* TREND HUNTER | SIX-STOCK TABLE WINDOWS", 1)[1]


def test_six_rows_then_scroll_each_leaderboard():
    assert "max-height: calc(40px + 6 * var(--th-stock-row-height))" in CUSTOM
    for selector in (".leaders-side .leader-list", "#volumeRatioView .leader-list", "#changeView .leader-list"):
        assert selector in CUSTOM
    assert "overflow-y: auto !important" in CUSTOM
    assert "LEADERBOARD_MAX_STOCKS = 10" in HTML


def test_sector_flow_uses_full_height_not_fixed_height():
    assert "#sectorFlow .flow-bar-zone" in CUSTOM
    assert "flex: 1 1 0" in CUSTOM
    assert "height: auto" in CUSTOM
    assert "height:max(5px, ${heightPercent.toFixed(2)}%)" in HTML
    assert "const chartHeight = mobileFlow ? 130 : 320" not in HTML
    assert "const baseline = flowTotal > 0 ? Math.min(70, Math.max(30" in HTML
    assert 'container.querySelectorAll(".flow-row").forEach(row => row.addEventListener("click"' in HTML


def test_one_screen_and_css_sync_preserved():
    assert "ONE-SCREEN WORKSPACE" in CSS
    assert "overflow: hidden !important" in CSS
    embedded = HTML.split('<style id="pulse-spectra-premium">', 1)[1].split("</style>", 1)[0]
    assert embedded.strip() == CSS.strip()
