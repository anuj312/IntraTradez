"""Ensure every sector stays in a single row on phones and docs are organized."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / 'intraday-momentum-scanner.html').read_text(encoding='utf8')
CSS = (ROOT / 'premium-terminal.css').read_text(encoding='utf8')
MOBILE_CSS = (ROOT / 'mobile-premium.css').read_text(encoding='utf8')


def test_dynamic_sector_column_count_in_renderer():
    assert 'container.style.setProperty("--th-sector-count", String(Math.max(1, items.length)));' in HTML
    assert '--th-sector-count' in CSS
    assert 'grid-template-columns: repeat(var(--th-sector-count, 15), minmax(0, 1fr)) !important;' in CSS
    assert 'grid-template-rows: minmax(0, 1fr) !important' in CSS
    assert 'grid-auto-flow: column !important' in CSS


def test_no_mobile_flow_scroll_and_consistent_editable_css():
    assert 'grid-template-columns: repeat(var(--th-sector-count, 15), minmax(0, 1fr)) !important' in MOBILE_CSS
    rules = re.findall(r'#sectorFlow \.flow-list \{[^}]+}', CSS)
    grid_rules = [rule for rule in rules if 'grid-template-columns: repeat(var(--th-sector-count' in rule]
    assert len(grid_rules) == 2
    assert any('overflow-x: hidden !important;' in rule and 'overflow-y: hidden !important;' in rule for rule in grid_rules)
    assert 'repeat(14, minmax(0, 1fr))' not in CSS


def test_all_project_md_files_are_in_mds():
    documents = sorted(p for p in ROOT.rglob('*.md') if not any(part.startswith('.') for part in p.relative_to(ROOT).parts))
    assert len(documents) >= 24
    assert all(p.parent == ROOT / 'MDS' for p in documents)
    assert (ROOT / 'MDS/README-live.md').exists()
    assert (ROOT / 'MDS/RAZORPAY_TEST_MODE_SETUP.md').exists()
