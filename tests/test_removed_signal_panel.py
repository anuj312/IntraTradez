"""The retired research strip must not return, while core dashboard features remain."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def test_removed_panel_and_js_handlers():
    html=(ROOT/'intraday-momentum-scanner.html').read_text(encoding='utf-8')
    css=(ROOT/'premium-terminal.css').read_text(encoding='utf-8')
    for old in ('signalPanel', 'Live signal intelligence', 'replayDate', 'replaySymbol',
                'replayBtn', 'futuresBtn', 'researchResults', 'renderSignals',
                'signalMeta', 'signalItems', '.signal-panel', '.signal-controls'):
        assert old not in html
        assert old not in css


def test_core_leaderboards_preserved():
    html=(ROOT/'intraday-momentum-scanner.html').read_text(encoding='utf-8')
    css=(ROOT/'premium-terminal.css').read_text(encoding='utf-8')
    for id_ in ('trackedValue', 'gainersList', 'losersList', 'volumeLeadersList',
                'volumeDeclinesList', 'changeLeadersList', 'changeDeclinesList',
                'sectorModal'):
        assert f'id="{id_}"' in html
    assert 'height: 497px !important;' in css
    assert 'overflow-y: auto !important;' in css
    assert (ROOT/'numbers.txt').exists()
