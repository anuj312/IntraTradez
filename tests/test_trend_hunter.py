"""Requested Trend Hunter UI changes must not regress."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_branding_and_hover_chart_removed():
    html=(ROOT/'intraday-momentum-scanner.html').read_text(encoding='utf8')
    assert '<title>Trend Hunter | Live Market Scanner</title>' in html
    assert '<div class="brand-name">Trend Hunter</div>' in html
    assert '<h1 id="pageTitle">Trend Hunter</h1>' in html
    assert ': "Trend Hunter";' in html
    for name in ('stockHoverChart','hoverCanvas','showStockHover','drawFiveMinuteChart','data-chart-symbol','chartDetails'):
        assert name not in html
    assert 'id="sectorModal"' in html
    assert 'data-tradingview-symbol' in html


def test_all_six_leaderboards_scroll_six_visible_rows():
    css=(ROOT/'premium-terminal.css').read_text(encoding='utf8')
    for selector in ('.leaders-side .leader-list', '#volumeRatioView .leader-list','#changeView .leader-list'):
        assert selector in css
    assert 'overflow-y: auto !important;' in css
    assert 'height: 497px !important;' in css
    assert 'height: auto !important;' in css
    html=(ROOT/'intraday-momentum-scanner.html').read_text(encoding='utf8')
    for id_ in ('gainersList','losersList','volumeLeadersList','volumeDeclinesList','changeLeadersList','changeDeclinesList'):
        assert f'id="{id_}"' in html


def test_existing_login_and_backend_not_changed():
    html=(ROOT/'intraday-momentum-scanner.html').read_text(encoding='utf8')
    assert '/api/access/login' in html
    assert 'access_session_id' in html
    assert (ROOT/'numbers.txt').is_file()
