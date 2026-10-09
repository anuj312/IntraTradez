"""One-screen layout contract: do not affect the internal stock lists."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "premium-terminal.css").read_text(encoding="utf-8")
HTML = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
BLOCK = CSS.split("/* TREND HUNTER | ONE-SCREEN WORKSPACE", 1)[1]


def test_document_and_workspace_are_viewport_locked():
    assert "height: 100dvh" in BLOCK
    assert "overflow: hidden !important" in BLOCK
    assert ".main {" in BLOCK
    assert "min-height: 0" in BLOCK
    assert "grid-template-rows: minmax(0, 1fr)" in BLOCK


def test_each_radar_keeps_its_own_scrollable_lists():
    for selector in (".leaders-side .leader-list", "#volumeRatioView .leader-list", "#changeView .leader-list"):
        assert selector in BLOCK
    assert "height: auto !important; flex: 1 1 0 !important" in BLOCK
    assert "overflow-y: auto !important" in BLOCK
    assert "scrollbar-width: thin !important" in BLOCK


def test_mobile_stacks_two_list_panels_but_not_page():
    assert "@media (max-width: 760px)" in BLOCK
    assert "grid-template-rows: repeat(2, minmax(0, 1fr)) !important" in BLOCK
    assert "overflow-x: auto; overflow-y: hidden;" in BLOCK
    assert "max-height: 60px" in BLOCK


def test_embedded_workspace_styles_are_current():
    assert "ONE-SCREEN WORKSPACE" in HTML
    embedded = HTML.split('<style id="pulse-spectra-premium">', 1)[1].split("</style>", 1)[0]
    assert embedded.strip() == CSS.strip()
