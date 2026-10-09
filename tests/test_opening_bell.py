"""Opening-bell behavior exercised without Kite credentials/network/Flask.

The actual functions are extracted from the production source with AST, not
reimplemented in the test, so wrong locking, filtering, or dates will fail.
"""
import ast
import math
import threading
import time
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
OPEN_BELL = datetime(2026, 10, 9, 9, 15, tzinfo=IST)


def load_functions(*names, clock=OPEN_BELL):
    tree = ast.parse((ROOT / "live_scanner_server.py").read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)] + nodes, type_ignores=[])

    class Clock:
        @staticmethod
        def now(_tz=None):
            return clock

        @staticmethod
        def fromtimestamp(*args, **kwargs):
            return datetime.fromtimestamp(*args, **kwargs)

    env = dict(IST=IST, datetime=Clock, time=time, math=math, pd=pd, timedelta=timedelta,
               TICK_STALE_SEC=20,
               DATA_LOCK=threading.RLock(), SYMBOL_TO_TOKEN={"BEL": 101, "BHEL": 102},
               TOKEN_TO_SYMBOL={101: "BEL", 102: "BHEL"}, TICK_STATE={},
               HISTORY={}, CANDLE_BUILDERS={}, LAST_CONFIRMED_CANDLE={},
               market_is_open=lambda now=None: dtime(9, 15) <= (now or clock).time() < dtime(15, 30),
               SECTOR_DEFINITIONS={}, ALL_SYMBOLS=["BEL", "BHEL"],
               PRIMARY_SECTOR={"BEL": "DEFENCE", "BHEL": "INDUSTRIAL"})
    exec(compile(ast.fix_missing_locations(module), "live_scanner_server.py", "exec"), env)
    return env


def test_tick_only_rows_available_at_0915_with_missing_history():
    env = load_functions("_as_float", "_live_quote_row", "_last_closed_five_minute", "_quote_first_rows", "_rank", "_directional_rank")
    env["TICK_STATE"][101] = {
        "ltp": 101.25, "volume": 12000, "day": OPEN_BELL.date(),
        "ohlc": {"open": 100, "close": 99.5}, "ts": time.time(),
    }
    row = env["_live_quote_row"]("BEL", "DEFENCE", OPEN_BELL)
    assert row["ltp"] == 101.25
    assert row["change"] == 1.25
    assert row["scoreStatus"] == "provisional"
    assert row["scoreSource"] == "live_quote_only"
    assert row["lastCompleted5m"] is None
    assert row["volumeBaselineReady"] is False
    assert row["ratio"] is None and row["rsi"] is None and row["adx"] is None

    # A yesterday-only cached row must not sneak into today's leaderboard.
    old = [{"symbol": "BHEL", "ltp": 999, "change": 8.0, "score": 100.0}]
    rows = env["_quote_first_rows"]("intraday", "stocks", "ALL", old)
    assert [r["symbol"] for r in rows] == ["BEL"]


def test_0920_confirms_first_5m_without_discarding_live_quote():
    at_0920 = OPEN_BELL + timedelta(minutes=5)
    env = load_functions("_as_float", "_live_quote_row", "_last_closed_five_minute", clock=at_0920)
    env["TICK_STATE"][101] = {
        "ltp": 104, "volume": 32000, "day": OPEN_BELL.date(),
        "ohlc": {"open": 100, "close": 99}, "ts": time.time(),
    }
    # This is exactly the *closed* 09:15-09:20 OHLC bar. 09:20's new
    # tick must not overwrite its 09:19:59 close.
    env["LAST_CONFIRMED_CANDLE"][101] = {
        "date": OPEN_BELL, "open": 100, "high": 103, "low": 100,
        "close": 102.5, "volume": 18000,
    }
    row = env["_live_quote_row"]("BEL", "DEFENCE", at_0920)
    assert row["ltp"] == 104
    assert row["lastCompleted5m"]["close"] == 102.5
    assert row["lastCompleted5m"]["momentumPct"] == 2.5
    assert row["lastCompleted5m"]["priceMomentumScore"] == 40.0
    assert row["lastCompleted5m"]["end"] == at_0920.isoformat()
    assert row["scoreStatus"] == "provisional"  # New 09:20 bar forming


def test_startup_and_html_quote_first_paths_exist():
    server = (ROOT / "live_scanner_server.py").read_text()
    html = (ROOT / "intraday-momentum-scanner.html").read_text()
    body = server[server.index("def initialize_live()") : server.index("def ensure_live_started()")]
    assert body.index("_start_ticker()") < body.index("_start_history_seed(force=False)")
    assert '"invalid_token"' in server and "kite.profile()" in server
    assert 'scanTimer = setInterval(() => { if (!document.hidden) loadLiveData(false); }, 3000);' in html
    assert 'Live / ${state.detailSymbols} detailed / ${state.universeSize} watched' in html
    assert 'const confirmation = completed5m ?' not in html
    assert 'current score provisional /' not in html
    assert 'last tick ${' not in html
    assert '${provisional ? "~" : ""}' not in html
    assert '${scoreMultiplier(row.score)}</span>' in html
    assert 'function hasVolumeRatio(row)' in html
