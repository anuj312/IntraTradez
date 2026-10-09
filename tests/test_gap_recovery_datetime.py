"""Regression: cached pandas timestamps must never reach Kite historical_data."""
import ast
import threading
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo('Asia/Kolkata')

class StrictKite:
    def __init__(self):
        self.calls = []
    def historical_data(self, token, start, end, interval, **kwargs):
        # Matches the strict 'type(x) == datetime.datetime' in pykiteconnect.
        assert type(start) is datetime, f'Non-native from date: {type(start)}'
        assert type(end) is datetime, f'Non-native to date: {type(end)}'
        assert start.tzinfo is None and end.tzinfo is None
        assert start < end
        self.calls.append((token, start, end, interval))
        return []


def load_functions():
    tree = ast.parse((ROOT / 'live_scanner_server.py').read_text())
    names = {'_kite_history_datetime', '_completed_history_cutoff', '_recover_history'}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + nodes, type_ignores=[])
    fake = StrictKite()
    env = {
        'IST': IST, 'pd': pd, 'datetime': datetime, 'timedelta': timedelta, 'dtime': dtime,
        'kite': fake, 'DATA_LOCK': threading.RLock(), 'HISTORY': {},
        'HISTORY_SLEEP_SEC': 0, 'SEED_DAYS_5M': 45, 'SEED_DAYS_DAILY': 120,
        'time': type('FakeTime', (), {'sleep': staticmethod(lambda _: None)}),
        'merge_finished': lambda before, after, **kwargs: pd.DataFrame(after),
        '_normalize_history': lambda candles: pd.DataFrame(candles),
    }
    exec(compile(ast.fix_missing_locations(module), 'live_scanner_server.py', 'exec'), env)
    return env, fake


def frame_for(ts):
    return pd.DataFrame([{'date': pd.Timestamp(ts), 'open': 100., 'high': 101., 'low': 99., 'close': 100., 'volume': 500}])


def test_caches_pandas_timestamp_becomes_native_datetime():
    env, fake = load_functions()
    env['HISTORY'][111] = {'intraday': frame_for('2026-10-09 11:00:00+05:30')}
    env['_recover_history']('BEL', 111, datetime(2026, 10, 9, 18, 39, tzinfo=IST))
    assert len(fake.calls) == 1
    assert fake.calls[0][1] == datetime(2026, 10, 9, 10, 55)
    assert fake.calls[0][2] == datetime(2026, 10, 9, 15, 30)
    assert fake.calls[0][3] == '5minute'


def test_after_close_complete_history_causes_no_request():
    env, fake = load_functions()
    env['HISTORY'][111] = {'intraday': frame_for('2026-10-09 15:25:00+05:30')}
    env['_recover_history']('BEL', 111, datetime(2026, 10, 9, 18, 39, tzinfo=IST))
    assert not fake.calls


def test_premarket_recovery_uses_previous_trading_day_close():
    env, fake = load_functions()
    env['HISTORY'][111] = {'intraday': frame_for('2026-10-08 15:15:00+05:30')}
    env['_recover_history']('BEL', 111, datetime(2026, 10, 9, 8, 50, tzinfo=IST))
    assert fake.calls[0][1] == datetime(2026, 10, 8, 15, 10)
    assert fake.calls[0][2] == datetime(2026, 10, 8, 15, 30)


def test_weekend_previous_trading_day_close():
    env, fake = load_functions()
    sunday = datetime(2026, 10, 11, 10, 0, tzinfo=IST)
    assert env['_completed_history_cutoff'](sunday) == datetime(2026, 10, 9, 15, 30, tzinfo=IST)
    monday_early = datetime(2026, 10, 12, 8, 45, tzinfo=IST)
    assert env['_completed_history_cutoff'](monday_early) == datetime(2026, 10, 9, 15, 30, tzinfo=IST)


def test_daily_recovery_cached_timestamp_uses_native_datetime():
    env, fake = load_functions()
    env['HISTORY'][111] = {
        'intraday': frame_for('2026-10-09 15:25:00+05:30'),
        'regular': frame_for('2026-10-08 00:00:00+05:30'),
    }
    env['_recover_history']('BEL', 111, datetime(2026, 10, 9, 18, 39, tzinfo=IST), daily=True)
    assert len(fake.calls) == 1
    assert fake.calls[0][3] == 'day'
    assert fake.calls[0][1] == datetime(2026, 10, 6, 0, 0)
    assert fake.calls[0][2] == datetime(2026, 10, 9, 18, 39)
