"""Regression coverage for the volume/% change mobile overlap incident."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / 'premium-terminal.css').read_text()
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text()


def test_volume_ratio_hidden_counterpart_specificity():
    assert '#volumeRatioView .leaders-grid[data-mobile-side-active="gainers"] > .leader-column.losers' in CSS
    assert '#volumeRatioView .leaders-grid[data-mobile-side-active="losers"] > .leader-column.gainers' in CSS
    assert 'display: none !important;' in CSS


def test_change_hidden_counterpart_specificity():
    assert '#changeView .leaders-grid[data-mobile-side-active="gainers"] > .leader-column.losers' in CSS
    assert '#changeView .leaders-grid[data-mobile-side-active="losers"] > .leader-column.gainers' in CSS


def test_mobile_tables_distinct_and_compact():
    assert '#volumeRatioView .volume-ratio-table col:nth-child(3)' in CSS
    assert '#changeView .score-table col:nth-child(4)' in CSS
    for short_header in ('CHG %', 'SCORE', 'VOL X'):
        assert f'content: "{short_header}"' in CSS
    assert '#changeView .leader-name' in CSS
    assert '#volumeRatioView .leader-copy' in CSS


def test_mobile_tabs_keep_selection_mechanism():
    assert 'data-mobile-side-active="gainers"' in HTML
    assert 'grid.dataset.mobileSideActive = button.dataset.mobileSide' in HTML
    assert 'item.scrollIntoView({ block: "nearest", inline: "nearest" })' in HTML


def test_backend_and_login_unmodified():
    assert 'numbers.txt' in (ROOT / 'live_scanner_server.py').read_text()
