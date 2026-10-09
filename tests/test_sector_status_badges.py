"""Sector popup badges are themed, mobile-safe and display correct live state."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'intraday-momentum-scanner.html'
CSS = ROOT / 'premium-terminal.css'


def test_badge_states_and_mobile_theme():
    html = HTML.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    assert '${sectorMomentumBadge(row)}' in html
    assert 'class="sector-state-badge sector-state--${variant}"' in html
    assert 'row.asOf && row.fresh === false' in html
    for status in ('accelerating', 'steady', 'fading', 'stale', 'waiting'):
        assert f'sector-state--{status}' in css
        assert f'body.theme-dark .sector-state--{status}' in css
    assert '.sector-stock-info { flex-direction: column;' in css
    assert 'prefers-reduced-motion: reduce' in css
    inline_css = re.search(r'<style id="pulse-spectra-premium">\s*(.*?)\s*</style>', html, re.S).group(1).strip()
    assert inline_css == css.strip()


def test_badge_runtime_js():
    html = HTML.read_text(encoding='utf-8')
    func = html.split('function sectorMomentumBadge(row) {', 1)[1].split('function openSectorModal(sector) {',1)[0]
    source = '''
    function escapeHtml(value) {return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");}
    function sectorMomentumBadge(row) {'''+func+'''
    const assert = require('node:assert/strict');
    assert.match(sectorMomentumBadge({momentumState:'accelerating',asOf:'2026-10-09',fresh:true}), /sector-state--accelerating/);
    assert.match(sectorMomentumBadge({momentumState:'steady',asOf:'2026-10-09',fresh:true}), /sector-state--steady/);
    assert.match(sectorMomentumBadge({momentumState:'fading',asOf:'2026-10-09',fresh:true}), /sector-state--fading/);
    assert.match(sectorMomentumBadge({momentumState:'accelerating',asOf:'2026-10-09',fresh:false}), /sector-state--stale/);
    assert.match(sectorMomentumBadge({}), /sector-state--waiting/);
    assert.match(sectorMomentumBadge({momentumState:'<bad>',asOf:'2026-10-09',fresh:true}), /sector-state--steady/);
    console.log('Sector status badge runtime checks passed');
    '''
    result = subprocess.run(['node','-e',source],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
