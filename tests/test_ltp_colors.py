"""Direction-based price-change colors must work across all scanner leaderboards."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ltp_colors_work_for_all_three_renderers():
    html = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
    assert html.count('class="leader-ltp ${ltpPercentTone(row.change)}"') == 3
    assert 'const amount = Number(value);' in html
    assert 'amount === 0 ? "neutral"' in html
    for panel in ("gainersList", "losersList", "volumeLeadersList", "volumeDeclinesList", "changeLeadersList", "changeDeclinesList"):
        assert f'updateScrollingLeaderboard("{panel}",' in html


def test_positive_negative_override_dark_table_styles():
    html = (ROOT / "intraday-momentum-scanner.html").read_text(encoding="utf-8")
    css = (ROOT / "premium-terminal.css").read_text(encoding="utf-8")
    marker = '<style id="pulse-spectra-premium">'
    assert marker in html
    for rule in (
        '.leader-table td.leader-ltp.positive { color: var(--pos);',
        '.leader-table td.leader-ltp.negative { color: var(--neg);',
        '.leader-table td.leader-ltp.neutral { color: var(--muted);',
    ):
        assert rule in css
        assert rule in html
