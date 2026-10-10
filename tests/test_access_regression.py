"""Offline checks of the original phone-number allowlist and session routes.

Extract the routes to avoid requiring Kite/Flask/network connections during pytest.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class FakeApp:
    def post(self, path):
        return lambda fn: fn

    def get(self, path):
        return lambda fn: fn


def _load_routes():
    tree = ast.parse((ROOT / "live_scanner_server.py").read_text())
    names = {
        "normalize_access_number", "_prune_sessions", "access_session_is_active",
        "access_login", "access_logout", "_request_is_authorized", "scan", "stock_candles", "replay", "futures"
    }
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert {fn.name for fn in functions} == names
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + functions, type_ignores=[])
    env = {
        "app": FakeApp(),
        "jsonify": lambda value: value,
        "time": time,
        "threading": threading,
        "ACCESS_TTL_SEC": 43200,
        "ACCESS_SESSION_LOCK": threading.RLock(),
        "ACTIVE_ACCESS_SESSIONS": {},
        "clean_env": lambda value: str(value or "").strip(),
        "allowed_access_numbers": lambda: {"9000000000"},
        "ensure_live_started": lambda: None,
        "request": SimpleNamespace(args={}, headers={}, get_json=lambda silent=False: {}),
        "membership": SimpleNamespace(enabled=lambda: False),
    }
    exec(compile(ast.fix_missing_locations(module), "<isolated backend routes>", "exec"), env)
    return env


def test_original_phone_only_login_and_single_session():
    e = _load_routes()
    payload = {"phone": "9000000000", "session_id": "original-browser-session"}
    e["request"].get_json = lambda silent=False: payload
    assert e["access_login"]() == {"ok": True}
    assert e["access_session_is_active"]("9000000000", "original-browser-session")

    payload = {"phone": "9000000000", "session_id": "another-browser"}
    rejected, code = e["access_login"]()
    assert code == 409 and rejected["error"] == "already_logged_in"

    payload = {"phone": "8000000000", "session_id": "not-approved"}
    rejected, code = e["access_login"]()
    assert code == 403 and rejected["error"] == "not_allowed"

    payload = {"phone": "9000000000", "session_id": "another-browser"}
    assert e["access_logout"]() == {"ok": True}  # incorrect session cannot log out original
    assert e["access_session_is_active"]("9000000000", "original-browser-session")
    payload = {"phone": "9000000000", "session_id": "original-browser-session"}
    assert e["access_logout"]() == {"ok": True}
    assert not e["access_session_is_active"]("9000000000", "original-browser-session")


def test_new_endpoints_still_reject_missing_original_login():
    e = _load_routes()
    e["request"].args = {}
    for call in [lambda: e["scan"](), lambda: e["stock_candles"]("RELIANCE"),
                 lambda: e["replay"](), lambda: e["futures"]()]:
        reply, code = call()
        assert code == 403 and reply == {"error": "access_required"}
