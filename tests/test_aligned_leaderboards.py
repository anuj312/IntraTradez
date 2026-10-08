"""All three leaderboard pairs show seven visible rows, scroll to fifteen, and stay aligned."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf-8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf-8')


def test_all_three_pairs_are_aligned_after_rendering():
    assert 'function alignLeaderboardPair(' in HTML
    for pair in (
        'alignLeaderboardPair("gainersList", "losersList",',
        'alignLeaderboardPair("volumeLeadersList", "volumeDeclinesList",',
        'alignLeaderboardPair("changeLeadersList", "changeDeclinesList",',
    ):
        assert HTML.count(pair) == 1


def test_placeholder_rows_do_not_fabricate_stocks():
    assert 'tr.className = "leader-placeholder-row"' in HTML
    assert 'tr.setAttribute("aria-hidden", i !== actualCount ? "true" : "false")' in HTML
    assert 'visibleMax = Math.max(leftCount, rightCount)' in HTML
    assert 'body.querySelectorAll(".leader-placeholder-row")' in HTML
    assert 'No additional gainers' in HTML
    assert 'No additional decliners' in HTML


def test_seven_visible_rows_with_sticky_headers_and_scroll():
    assert 'height: 497px !important;' in CSS
    assert 'overflow-y: auto !important;' in CSS
    assert 'scrollbar-width: thin !important;' in CSS
    assert 'scrollbar-gutter: stable;' in CSS
    assert 'position: sticky;' in CSS
    assert 'align-items: stretch !important;' in CSS
    for id_ in ('gainersList', 'losersList', 'volumeLeadersList', 'volumeDeclinesList',
                'changeLeadersList', 'changeDeclinesList'):
        assert f'id="{id_}" role="region" tabindex="0"' in HTML


def test_maximum_fifteen_results_and_refresh_keeps_scroll():
    assert 'const LEADERBOARD_MAX_STOCKS = 15;' in HTML
    assert HTML.count('.slice(0, LEADERBOARD_MAX_STOCKS)') == 6
    assert HTML.count('updateScrollingLeaderboard("') == 6
    assert 'const oldTop = host.scrollTop;' in HTML
    assert 'host.scrollTop = oldTop;' in HTML
    assert '0 / 30' not in HTML


def test_premium_css_embedded_matches_editable_file():
    start = HTML.index('<style id="pulse-spectra-premium">') + len('<style id="pulse-spectra-premium">')
    end = HTML.index('</style>', start)
    assert HTML[start:end].strip() == CSS.strip()
