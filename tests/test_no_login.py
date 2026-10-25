"""Run: python3 -m unittest discover -s tests -v (no Kite credentials needed)."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_SERVER = (ROOT / 'live_scanner_server.py').read_text()
UI = (ROOT / 'intraday-momentum-scanner.html').read_text()

class PublicLiveScannerTests(unittest.TestCase):
    def test_python_valid(self):
        ast.parse(PY_SERVER)

    def test_no_membership_dependency(self):
        self.assertNotIn('import member_payments', PY_SERVER)
        self.assertNotIn('supabase', PY_SERVER.lower())
        self.assertNotIn('razorpay', PY_SERVER.lower())

    def test_no_membership_routes(self):
        self.assertNotRegex(PY_SERVER, r'@app\.(get|post)\(["\']/api/(access|membership|verify-payment|create-order)')

    def test_scan_routes_still_present(self):
        for endpoint in ('/', '/api/health', '/api/scan', '/api/stock/<symbol>/candles', '/api/replay', '/api/futures'):
            self.assertIn(f'@app.get("{endpoint}")', PY_SERVER)

    def test_no_access_gate_in_routes(self):
        self.assertNotIn('_request_is_authorized', PY_SERVER)
        self.assertNotIn('access_required', PY_SERVER)

    def test_no_auth_javascript(self):
        js = UI.split('<script>')[-1].split('</script>')[0]
        for forbidden in ('initializeAccess(', 'googleClient', 'membershipHeaders', 'accessSessionId', 'accessUrl(', 'accessGranted', 'logoutBtn'):
            self.assertNotIn(forbidden,js)
        self.assertIn('startScanPolling();',js)

    def test_login_and_payment_dom_removed(self):
        for forbidden in ('premium-access-gate', 'access-gate-form', 'id="logoutBtn"', 'checkout.razorpay.com', 'supabase.min.js'):
            self.assertNotIn(forbidden,UI)

    def test_all_live_panels_remain(self):
        for view in ('momentumView', 'volumeRatioView', 'changeView', 'sectorFlow'):
            self.assertIn(f'id="{view}"',UI)
        self.assertIn('id="sectorModal"',UI)
        self.assertIn('data-tradingview-symbol',UI)

    def test_public_scan_polling(self):
        self.assertRegex(UI, r'fetch\(`/api/scan\?\$\{params\.toString\(\)\}`')
        self.assertIn('body class="scanner-ready"',UI)

    def test_env_contains_no_login_payment_keys(self):
        example = (ROOT/'.env.example').read_text().lower()
        self.assertNotIn('supabase',example)
        self.assertNotIn('razorpay',example)
        self.assertIn('kite_access_token=',example)

if __name__ == '__main__':
    unittest.main()
