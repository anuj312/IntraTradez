from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def test_original_numbers_txt_auth_restored():
    server = (ROOT / "live_scanner_server.py").read_text()
    html = (ROOT / "intraday-momentum-scanner.html").read_text()
    assert 'allowed_access_numbers()' in server
    assert '@app.post("/api/access/login")' in server
    assert 'access_session_is_active(phone, session_id)' in server
    assert '/api/access/login' in html
    assert '/api/access/request-otp' not in html
    assert '/api/access/verify-otp' not in html
    assert 'access_phone' in html and 'access_session_id' in html
    assert 'data-chart-symbol' not in html  # removed as requested
    assert 'rankRows(buildRows())' not in html
    assert (ROOT / 'numbers.txt').is_file()
    for banned in ('TWILIO_', 'request-otp', 'verify-otp', 'COOKIE_NAME', '_verified_phone'):
        assert banned not in server

def test_original_render_config_restored():
    conf = (ROOT / 'render.yaml').read_text()
    assert 'rootDir: outputs' in conf
    assert 'uvicorn app:app' in conf
    assert 'gunicorn app:app' not in conf
    assert 'mountPath: /var/data' not in conf
    assert 'TWILIO_' not in conf
