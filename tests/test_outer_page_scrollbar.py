"""The dashboard fits the viewport without document scrolling; lists scroll."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "premium-terminal.css").read_text(encoding="utf-8")
HTML = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")


def test_document_scrollbar_only_is_hidden():
    assert "html::-webkit-scrollbar,\nbody::-webkit-scrollbar" in CSS
    assert "scrollbar-width: none !important" in CSS
    workspace = CSS.split("/* TREND HUNTER | ONE-SCREEN WORKSPACE", 1)[1]
    assert "overflow: hidden !important" in workspace
    assert "height: 100dvh" in workspace
    assert "scrollbar-width: none !important" in HTML


def test_stock_list_scrollbars_are_preserved():
    assert ".leaders-side .leader-list" in CSS
    assert "#volumeRatioView .leader-list" in CSS
    assert "#changeView .leader-list" in CSS
    assert "overflow-y: auto !important" in CSS
    assert "scrollbar-width: thin !important" in CSS
    assert ".leaders-side .leader-list::-webkit-scrollbar" in CSS
    assert "#volumeRatioView .leader-list::-webkit-scrollbar" in CSS
    assert "#changeView .leader-list::-webkit-scrollbar" in CSS
    assert "height: auto !important; flex: 1 1 0 !important" in CSS


def test_embedded_css_stays_synced():
    start = '<style id="pulse-spectra-premium">\n'
    assert start + CSS.rstrip() + "\n</style>" in HTML
