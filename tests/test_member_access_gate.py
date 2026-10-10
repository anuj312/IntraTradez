"""Regression checks for the Black Label registered-number visibility gate."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf-8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf-8')
BACKEND = (ROOT / 'live_scanner_server.py').read_text(encoding='utf-8')


def test_four_views_have_individual_membership_gates():
    assert HTML.count('class="access-cta premium-access-gate"') == 4
    assert HTML.count('class="member-preview member-preview-leaders"') == 3
    assert HTML.count('class="member-preview member-preview-flow"') == 1
    assert HTML.count('class="access-form access-gate-form"') == 4
    assert HTML.count('class="access-error" role="alert" hidden') == 4
    assert HTML.count('member-gated') >= 4
    for name in ('Momentum Radar', 'Volume Radar', '% Change Radar', 'Sector Flow'):
        assert f'aria-label="Registered members only — {name}"' in HTML


def test_locked_content_blurs_but_unlock_removes_preview():
    assert 'body:not(.access-granted) .member-gated > .leaders-grid' in CSS
    assert 'body:not(.access-granted) #sectorFlow > .flow-list' in CSS
    assert 'filter: blur(9px) saturate(.7) !important' in CSS
    assert 'body.access-granted .member-gated > .premium-access-gate { display: none !important; }' in CSS
    assert 'body.access-granted .member-gated > .member-preview { display: none !important; }' in CSS


def test_no_stock_values_are_placed_in_an_unauthorized_preview():
    assert 'class="demo-stock-row"' in HTML
    # Static placeholders contain no pre-filled live ticker names or stock prices.
    preview=HTML.split('class="member-preview member-preview-leaders"', 1)[1].split('<div class="access-cta premium-access-gate"',1)[0]
    for name in ('BEL', 'TCS', 'RELIANCE', 'COLPAL', 'MAZDOCK'):
        assert name not in preview


def test_logout_discards_cached_data_and_late_scan_response():
    assert 'let accessGeneration = 0;' in HTML
    assert 'generation !== accessGeneration' in HTML
    assert 'node.replaceChildren()' in HTML
    assert 'state.liveRows = null;' in HTML
    assert 'accessStorageRemove("scannerAccessNumber")' in HTML


def test_backend_restricts_scan_stock_candles_replay_and_futures():
    module=ast.parse(BACKEND)
    names={'scan','stock_candles','replay','futures'}
    for fn in module.body:
        if isinstance(fn,ast.FunctionDef) and fn.name in names:
            source=ast.get_source_segment(BACKEND,fn)
            assert '_request_is_authorized()' in source
            assert '"access_required"' in source
            names.remove(fn.name)
    assert not names
    assert 'access_session_is_active(phone, session_id)' in BACKEND
    assert 'membership.has_paid_access(membership.bearer_token())' in BACKEND
    assert 'numbers.txt' in BACKEND
    assert '/api/access/request-otp' not in BACKEND
