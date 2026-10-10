"""
Live backend for intraday-momentum-scanner.html (Flask / WSGI).

Recommended Render start command (Gunicorn):
  gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 8 --timeout 120

Notes:
- Kite credentials stay server-side (KITE_API_KEY, KITE_ACCESS_TOKEN).
- /api/scan is protected by phone+session_id via /api/access/login.
- This version REMOVES the public /numbers.txt endpoint (privacy). Update the HTML to
  stop fetching numbers.txt and rely on /api/access/login response instead.
"""

from __future__ import annotations

import logging
import math
import os
import pickle
import threading
import time
from collections import deque
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Flask, Response, jsonify, request, send_file

try:
    # Optional but strongly recommended (bandwidth saver on free hosting).
    from flask_compress import Compress  # type: ignore
except Exception:  # pragma: no cover
    Compress = None  # type: ignore

from kiteconnect import KiteConnect, KiteTicker
from kiteconnect.exceptions import TokenException

from sector_definitions import ALL_SYMBOLS, SECTOR_DEFINITIONS
import member_payments as membership

from scanner_features import FiveMinuteBuilder, market_bucket, merge_finished, cumulative_slot_ratio, one_way_metrics, breakout_signals, replay_session


# ----------------------------
# Config / Globals
# ----------------------------

BASE_DIR = Path(__file__).resolve().parent
IST = ZoneInfo("Asia/Kolkata")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("momentum-scanner")


def clean_env(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


def parse_clock(value: str, fallback: dtime) -> dtime:
    try:
        hour, minute = (int(part) for part in clean_env(value).split(":", 1))
        return dtime(hour, minute)
    except (TypeError, ValueError):
        return fallback


API_KEY = clean_env(os.getenv("KITE_API_KEY", ""))
ACCESS_TOKEN = clean_env(os.getenv("KITE_ACCESS_TOKEN", ""))

# Prefer persistent disk path if you attach one on Render.
DATA_DIR = Path(clean_env(os.getenv("SCANNER_DATA_DIR", "/var/data")))
if not DATA_DIR.exists():
    DATA_DIR = BASE_DIR / ".runtime"
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    DATA_DIR = BASE_DIR / ".runtime"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_CACHE_PATH = DATA_DIR / "history-cache.pkl"
HISTORY_WRITE_LOCK = threading.Lock()

HISTORY_SLEEP_SEC = float(os.getenv("HISTORY_SLEEP_SEC", "0.35"))
SEED_DAYS_5M = int(os.getenv("SEED_DAYS_5M", "45"))
SEED_DAYS_DAILY = int(os.getenv("SEED_DAYS_DAILY", "120"))

TICK_STALE_SEC = int(os.getenv("TICK_STALE_SEC", "20"))

PORT = int(os.getenv("PORT", "8050"))

FAST_MODE = os.getenv("FAST_MODE", "false").strip().lower() not in {"0", "false", "no", "off"}
FAST_SYMBOL_LIMIT = int(os.getenv("FAST_SYMBOL_LIMIT", "25"))
FAST_SELECTION_WAIT_SEC = int(os.getenv("FAST_SELECTION_WAIT_SEC", "20"))
FAST_RESELECT_SEC = int(os.getenv("FAST_RESELECT_SEC", "300"))

SCAN_COMPUTE_EVERY_SEC = float(os.getenv("SCAN_COMPUTE_EVERY_SEC", "8"))
INVALID_KITE_TOKEN = False

PREMARKET_SEED_TIME = parse_clock(os.getenv("PREMARKET_SEED_TIME", "07:30"), dtime(7, 30))

# API payload sizing (bandwidth control)
DEFAULT_SCAN_LIMIT = int(os.getenv("DEFAULT_SCAN_LIMIT", "250"))
MAX_SCAN_LIMIT = int(os.getenv("MAX_SCAN_LIMIT", "2000"))

# Access session TTL (memory safety)
ACCESS_TTL_SEC = int(os.getenv("ACCESS_TTL_SEC", "43200"))  # 12 hours
ENABLE_FUTURES_OI = os.getenv("ENABLE_FUTURES_OI", "false").lower() == "true"
PRIMARY_SECTOR = {symbol: group for group, symbols in reversed(list(SECTOR_DEFINITIONS.items()))
                  if group != "NIFTY_50" for symbol in symbols}
SECTOR_MEMBERSHIP = {symbol: {group for group, symbols in SECTOR_DEFINITIONS.items() if symbol in symbols}
                     for symbol in ALL_SYMBOLS}
INDUSTRY_GROUPS = {name: symbols for name, symbols in SECTOR_DEFINITIONS.items() if name != "NIFTY_50"}


app = Flask(__name__)
if Compress is not None:
    Compress(app)

kite: Optional[KiteConnect] = None
SYMBOL_TO_TOKEN: Dict[str, int] = {}
TOKEN_TO_SYMBOL: Dict[int, str] = {}
INDEX_TO_TOKEN: Dict[str, int] = {}
INDEX_TOKEN_TO_SYMBOL: Dict[int, str] = {}

TICK_STATE: Dict[int, Dict[str, Any]] = {}
PRICE_HISTORY: Dict[int, deque] = {}
HISTORY: Dict[int, Dict[str, pd.DataFrame]] = {}
CANDLE_BUILDERS: Dict[int, FiveMinuteBuilder] = {}
LAST_CONFIRMED_CANDLE: Dict[int, dict] = {}
VOLUME_PROFILE_CACHE: Dict[int, tuple] = {}
SCORE_HISTORY: Dict[str, deque] = {}
FUTURES_TOKENS: Dict[int, str] = {}
FUTURES_QUOTES: Dict[int, dict] = {}
RECOVERY_STARTED = False
RECOVERY_LOCK = threading.Lock()

DATA_LOCK = threading.RLock()
LAST_TICK_TS = 0.0
TOTAL_TICKS = 0
TICKER_CONNECTED = False
TICKER_STARTED = False
TICKER_WS: Any = None

LIVE_INITIALIZED = False
LIVE_INIT_LOCK = threading.Lock()

SEED_PROGRESS = {"done": 0, "total": 0, "errors": 0}
DETAIL_SYMBOLS: set[str] = set()

SEED_IN_PROGRESS = False
FAST_SEED_IN_PROGRESS = False
FAST_ROTATION_STARTED = False

HISTORY_SEED_DATE: Optional[date] = None          # date of last successful seed
SEED_REQUESTED_DATE: Optional[date] = None        # date currently requested/running

HISTORY_CACHE_LOADED = False

DAILY_REFRESH_STARTED = False
DAILY_REFRESH_REQUESTED_DATE: Optional[date] = None
DAILY_REFRESH_START_LOCK = threading.Lock()

# Cache computed scan rows to keep /api/scan cheap.
SCAN_CACHE: Dict[str, Dict[str, List[dict]]] = {
    "intraday": {"stocks": [], "index": []},
    "regular": {"stocks": [], "index": []},
}
SECTOR_FLOW_CACHE: List[dict] = []
SCAN_CACHE_UPDATED_AT = 0.0
LAST_CACHE_SAVE_AT = 0.0
SCAN_COMPUTE_STARTED = False
SCAN_CACHE_LOCK = threading.RLock()
SCAN_COMPUTE_START_LOCK = threading.Lock()

# Access session store: phone -> {"session_id": str, "ts": float}
ACCESS_SESSION_LOCK = threading.RLock()
ACTIVE_ACCESS_SESSIONS: Dict[str, Dict[str, Any]] = {}

# Allowlist cache (avoid reading file every request)
ALLOWLIST_LOCK = threading.RLock()
ALLOWLIST_CACHE: set[str] = set()
ALLOWLIST_CACHE_TS = 0.0
ALLOWLIST_CACHE_TTL_SEC = int(os.getenv("ALLOWLIST_CACHE_TTL_SEC", "60"))


# ----------------------------
# Access control
# ----------------------------

def normalize_access_number(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[2:] if digits.startswith("91") and len(digits) == 12 else digits


def _load_allowlist() -> set[str]:
    try:
        values = (BASE_DIR / "numbers.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {normalize_access_number(value) for value in values if normalize_access_number(value)}


def allowed_access_numbers() -> set[str]:
    global ALLOWLIST_CACHE, ALLOWLIST_CACHE_TS
    now = time.time()
    with ALLOWLIST_LOCK:
        if (now - ALLOWLIST_CACHE_TS) <= ALLOWLIST_CACHE_TTL_SEC and ALLOWLIST_CACHE:
            return set(ALLOWLIST_CACHE)
        ALLOWLIST_CACHE = _load_allowlist()
        ALLOWLIST_CACHE_TS = now
        return set(ALLOWLIST_CACHE)


def _prune_sessions(now: Optional[float] = None) -> None:
    now = now or time.time()
    with ACCESS_SESSION_LOCK:
        expired = [
            phone for phone, record in ACTIVE_ACCESS_SESSIONS.items()
            if (now - float(record.get("ts") or 0.0)) > ACCESS_TTL_SEC
        ]
        for phone in expired:
            ACTIVE_ACCESS_SESSIONS.pop(phone, None)


def access_session_is_active(phone: str, session_id: str) -> bool:
    if not phone or not session_id:
        return False
    now = time.time()
    _prune_sessions(now)
    with ACCESS_SESSION_LOCK:
        record = ACTIVE_ACCESS_SESSIONS.get(phone)
        if not record:
            return False
        if record.get("session_id") != session_id:
            return False
        # Touch session
        record["ts"] = now
        return True


# ----------------------------
# Market status helpers
# ----------------------------

def market_is_open(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return dtime(9, 15) <= now.time() <= dtime(15, 30)


def _has_current_session_data(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(IST)
    if LAST_TICK_TS and datetime.fromtimestamp(LAST_TICK_TS, IST).date() == now.date():
        return True
    with DATA_LOCK:
        for histories in HISTORY.values():
            for frame in histories.values():
                if not frame.empty and frame.iloc[-1]["date"].date() == now.date():
                    return True
    return False


def _feed_status() -> tuple[str, bool]:
    """
    status values used by frontend:
      - live
      - seeding
      - previous_session
      - market_closed
      - waiting_for_ticks
      - missing_credentials
    """
    now = datetime.now(IST)

    if INVALID_KITE_TOKEN:
        return "invalid_token", False

    if kite is None or not SYMBOL_TO_TOKEN:
        return "missing_credentials", False

    if not market_is_open(now):
        # Distinguish post-close if we did see today's data.
        if now.weekday() < 5 and now.time() > dtime(15, 30) and _has_current_session_data(now):
            return "market_closed", False
        return "previous_session", False

    fresh = LAST_TICK_TS and (time.time() - LAST_TICK_TS) <= TICK_STALE_SEC

    if TICKER_CONNECTED and fresh:
        return "live", True

    if SEED_IN_PROGRESS:
        return "seeding", False

    if not _has_current_session_data(now):
        return "previous_session", False

    return "waiting_for_ticks", False


def _official_nifty_quote() -> Optional[dict]:
    """Return the live NIFTY 50 quote when Kite exposes the NSE index token."""
    with DATA_LOCK:
        token = INDEX_TO_TOKEN.get("NIFTY 50")
        tick = dict(TICK_STATE.get(token) or {}) if token else {}
    ltp = _as_float(tick.get("ltp"))
    ohlc = tick.get("ohlc") if isinstance(tick.get("ohlc"), dict) else {}
    open_price = _as_float(ohlc.get("open"))
    if not ltp or not open_price:
        return None
    return {
        "symbol": "NIFTY 50",
        "ltp": round(ltp, 2),
        "change": round((ltp - open_price) / (open_price + 1e-9) * 100.0, 2),
        "updated_at": datetime.fromtimestamp(float(tick.get("ts") or 0.0), IST).isoformat() if tick.get("ts") else None,
    }


# ----------------------------
# Numeric helpers
# ----------------------------

def _as_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _order_book_delta(depth: dict) -> Optional[float]:
    """Return resting bid-vs-ask quantity imbalance from Kite full-mode depth."""
    buy = sum(_as_float(level.get("quantity")) or 0.0 for level in (depth.get("buy") or [])[:5])
    sell = sum(_as_float(level.get("quantity")) or 0.0 for level in (depth.get("sell") or [])[:5])
    total = buy + sell
    if total <= 0:
        return None
    return (buy - sell) / total


# ----------------------------
# History cache load/save
# ----------------------------

def _to_ist_series(values: pd.Series) -> pd.Series:
    dates = pd.to_datetime(values, errors="coerce")
    if dates.dt.tz is None:
        return dates.dt.tz_localize(IST)
    return dates.dt.tz_convert(IST)


def _normalize_history(candles: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(candles)
    if frame.empty:
        return frame
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame["date"] = _to_ist_series(frame["date"])
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)


def _load_history_cache() -> bool:
    global HISTORY_CACHE_LOADED, HISTORY_SEED_DATE, SEED_REQUESTED_DATE
    if not HISTORY_CACHE_PATH.exists():
        return False
    try:
        with HISTORY_CACHE_PATH.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            return False
        if payload.get("version") != 1 or not payload.get("complete"):
            return False

        cached_date = date.fromisoformat(str(payload["seed_date"]))
        cached_history = payload.get("history") or {}
        loaded = 0
        with DATA_LOCK:
            for symbol, histories in cached_history.items():
                token = SYMBOL_TO_TOKEN.get(symbol)
                if not token or not isinstance(histories, dict):
                    continue
                frames = {
                    name: frame
                    for name, frame in histories.items()
                    if name in {"intraday", "regular"} and isinstance(frame, pd.DataFrame) and not frame.empty
                }
                if frames:
                    HISTORY[token] = frames
                    loaded += 1

        if not loaded:
            return False

        HISTORY_SEED_DATE = cached_date
        SEED_REQUESTED_DATE = cached_date
        HISTORY_CACHE_LOADED = True
        log.info("Loaded history cache: %s symbols from %s", loaded, HISTORY_CACHE_PATH)
        return True
    except Exception:
        log.exception("Unable to load persisted history cache")
        return False


def _save_history_cache(seed_date: date) -> None:
    with HISTORY_WRITE_LOCK:
        _write_history_cache(seed_date)


def _write_history_cache(seed_date: date) -> None:
    with DATA_LOCK:
        cached_history = {
            TOKEN_TO_SYMBOL[token]: histories
            for token, histories in HISTORY.items()
            if token in TOKEN_TO_SYMBOL and histories
        }
    if not cached_history:
        return
    payload = {"version": 1, "complete": True, "seed_date": seed_date.isoformat(), "history": cached_history}
    temporary_path = HISTORY_CACHE_PATH.with_suffix(".tmp")
    try:
        HISTORY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with temporary_path.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary_path, HISTORY_CACHE_PATH)
        log.info("Persisted history cache: %s symbols", len(cached_history))
    except OSError:
        log.exception("Unable to persist history cache")


# ----------------------------
# Kite init + ticker
# ----------------------------

def load_instruments() -> None:
    global kite, INVALID_KITE_TOKEN
    if not API_KEY or not ACCESS_TOKEN:
        log.warning("Kite credentials missing; dashboard remains offline (never simulated).")
        return

    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)

    # Abort before the history loop if today's Kite access token has expired.
    # Historical requests must never be used to diagnose a bad session one
    # symbol at a time (that causes hundreds of TokenException logs).
    try:
        kite.profile()
        INVALID_KITE_TOKEN = False
    except TokenException:
        INVALID_KITE_TOKEN = True
        kite = None
        log.error("Kite access token invalid/expired: refresh KITE_ACCESS_TOKEN before market open")
        return

    frame = pd.DataFrame(kite.instruments("NSE"))
    if frame.empty or "tradingsymbol" not in frame.columns:
        raise RuntimeError("Kite returned no NSE instruments")

    stock_frame = frame[frame["tradingsymbol"].isin(ALL_SYMBOLS)].copy()
    index_frame = frame[frame["tradingsymbol"].isin({"NIFTY 50", "NIFTY50"})].copy()

    with DATA_LOCK:
        SYMBOL_TO_TOKEN.clear()
        TOKEN_TO_SYMBOL.clear()
        INDEX_TO_TOKEN.clear()
        INDEX_TOKEN_TO_SYMBOL.clear()
        for row in stock_frame.itertuples(index=False):
            SYMBOL_TO_TOKEN[str(row.tradingsymbol)] = int(row.instrument_token)
            TOKEN_TO_SYMBOL[int(row.instrument_token)] = str(row.tradingsymbol)
        for row in index_frame.itertuples(index=False):
            name = "NIFTY 50" if str(row.tradingsymbol) in {"NIFTY 50", "NIFTY50"} else None
            if name and name not in INDEX_TO_TOKEN:
                INDEX_TO_TOKEN[name] = int(row.instrument_token)
                INDEX_TOKEN_TO_SYMBOL[int(row.instrument_token)] = name

    if ENABLE_FUTURES_OI:
        try:
            nfo = pd.DataFrame(kite.instruments("NFO"))
            if not nfo.empty and {"instrument_type", "name", "expiry", "instrument_token"}.issubset(nfo.columns):
                f = nfo[(nfo["instrument_type"] == "FUT") & (nfo["name"].isin(ALL_SYMBOLS))].copy()
                f["expiry"] = pd.to_datetime(f["expiry"]).dt.date
                f = f[f["expiry"] >= datetime.now(IST).date()].sort_values("expiry").drop_duplicates("name")
                with DATA_LOCK:
                    FUTURES_TOKENS.clear()
                    FUTURES_TOKENS.update({int(row.instrument_token): str(row.name) for row in f.itertuples()})
                log.info("Optional FUTSTK OI tracking: %s near-expiry contracts", len(FUTURES_TOKENS))
        except Exception:
            log.exception("Optional futures OI instruments unavailable; cash scanner continues")

    missing = sorted(set(ALL_SYMBOLS) - set(SYMBOL_TO_TOKEN))
    log.info("Loaded %s/%s NSE symbols", len(SYMBOL_TO_TOKEN), len(ALL_SYMBOLS))
    log.info("Loaded official index quotes: %s", ", ".join(sorted(INDEX_TO_TOKEN)) or "none")
    if missing:
        log.warning("Symbols missing in Kite NSE instruments: %s", ", ".join(missing))


def _append_closed(token: int, candle: dict) -> None:
    if not candle or candle.get("volume", 0) < 0:
        return
    histories = HISTORY.setdefault(token, {})
    histories["intraday"] = merge_finished(histories.get("intraday"), [candle])
    LAST_CONFIRMED_CANDLE[token] = dict(candle)


def _flush_completed_candles(now: datetime) -> None:
    with DATA_LOCK:
        for token, builder in CANDLE_BUILDERS.items():
            if builder.start is not None and builder.candle and now >= builder.start + timedelta(minutes=5):
                _append_closed(token, builder.partial())
                builder.candle = None
                builder.start = None


def _update_tick(tick: dict) -> None:
    token = tick.get("instrument_token")
    ltp = _as_float(tick.get("last_price"))
    if token is None or ltp is None or ltp <= 0:
        return
    token = int(token)
    if token in FUTURES_TOKENS:
        oi = _as_float(tick.get("oi"))
        if oi is not None:
            original = FUTURES_QUOTES.get(token)
            if original is None or original.get("day") != datetime.now(IST).date():
                FUTURES_QUOTES[token] = {"day": datetime.now(IST).date(), "base_oi": oi,
                                         "base_price": ltp, "oi": oi, "ltp": ltp, "ts": time.time()}
            else:
                original.update({"oi": oi, "ltp": ltp, "ts": time.time()})
        return
    if token not in TOKEN_TO_SYMBOL and token not in INDEX_TOKEN_TO_SYMBOL:
        return
    timestamp = tick.get("exchange_timestamp") or tick.get("last_trade_time")
    if isinstance(timestamp, datetime):
        timestamp = timestamp.replace(tzinfo=IST) if timestamp.tzinfo is None else timestamp.astimezone(IST)
    else:
        timestamp = datetime.now(IST)
    ts = time.time()
    ohlc = tick.get("ohlc") or {}
    depth_imbalance = _order_book_delta(tick.get("depth") or {})
    previous = TICK_STATE.get(token) or {}
    volume = _as_float(tick.get("volume_traded"))
    if volume is None:
        volume = _as_float(previous.get("volume")) or 0.
    if previous.get("day") != timestamp.date():
        CANDLE_BUILDERS.pop(token, None)
    TICK_STATE[token] = {"ltp": ltp, "volume": volume, "ohlc": ohlc,
                         "depth_imbalance": depth_imbalance, "ts": ts, "day": timestamp.date()}
    PRICE_HISTORY.setdefault(token, deque(maxlen=3600)).append((ts, ltp, volume, depth_imbalance))
    if token in TOKEN_TO_SYMBOL and market_bucket(timestamp) is not None:
        builder = CANDLE_BUILDERS.setdefault(token, FiveMinuteBuilder())
        baseline = 0.
        if builder.previous_total is None:
            frame = HISTORY.get(token, {}).get("intraday")
            if frame is not None and not frame.empty:
                finished = frame[frame["date"].dt.date == timestamp.date()]
                baseline = float(finished["volume"].sum()) if not finished.empty else 0.
        closed = builder.ingest(timestamp, ltp, volume, baseline)
        if closed:
            _append_closed(token, closed)


def _set_ticker_modes(selected_symbols: set[str]) -> None:
    with DATA_LOCK:
        ticker_ws = TICKER_WS
        all_tokens = sorted(set(TOKEN_TO_SYMBOL) | set(INDEX_TOKEN_TO_SYMBOL) | set(FUTURES_TOKENS))
        selected_tokens = [SYMBOL_TO_TOKEN[symbol] for symbol in selected_symbols if symbol in SYMBOL_TO_TOKEN]
    if not ticker_ws:
        return
    try:
        ticker_ws.set_mode(ticker_ws.MODE_QUOTE, all_tokens)
        full_tokens = sorted(set(selected_tokens) | set(FUTURES_TOKENS))
        if full_tokens:
            ticker_ws.set_mode(ticker_ws.MODE_FULL, full_tokens)
    except Exception:
        log.exception("Unable to update Fast mode ticker subscriptions")


def _start_ticker() -> None:
    global TICKER_STARTED, TICKER_CONNECTED, TICKER_WS
    if TICKER_STARTED or kite is None or not SYMBOL_TO_TOKEN:
        return

    TICKER_STARTED = True
    tokens = sorted(set(TOKEN_TO_SYMBOL) | set(INDEX_TOKEN_TO_SYMBOL) | set(FUTURES_TOKENS))

    def run() -> None:
        global TICKER_CONNECTED, TICKER_WS, LAST_TICK_TS, TOTAL_TICKS

        while True:
            closed = threading.Event()

            try:
                ticker = KiteTicker(API_KEY, ACCESS_TOKEN, reconnect=False)

                def on_connect(ws, _response):
                    global TICKER_CONNECTED, TICKER_WS
                    TICKER_WS = ws
                    ws.subscribe(tokens)
                    ws.set_mode(ws.MODE_QUOTE, tokens)

                    # FULL mode only for selected detail symbols (may be empty).
                    with DATA_LOCK:
                        selected_tokens = [SYMBOL_TO_TOKEN[s] for s in DETAIL_SYMBOLS if s in SYMBOL_TO_TOKEN]
                    full_tokens = sorted(set(selected_tokens) | set(FUTURES_TOKENS))
                    if full_tokens:
                        ws.set_mode(ws.MODE_FULL, full_tokens)

                    TICKER_CONNECTED = True
                    if HISTORY and not SEED_IN_PROGRESS:
                        _start_gap_recovery()
                    log.info(
                        "KiteTicker connected: %s quote tokens, %s full-depth tokens",
                        len(tokens),
                        len(selected_tokens),
                    )

                def on_ticks(_ws, ticks):
                    global LAST_TICK_TS, TOTAL_TICKS
                    with DATA_LOCK:
                        for tick in ticks:
                            _update_tick(tick)
                        if ticks:
                            TOTAL_TICKS += len(ticks)
                            LAST_TICK_TS = time.time()

                def on_close(_ws, _code, _reason):
                    global TICKER_CONNECTED, TICKER_WS
                    TICKER_CONNECTED = False
                    TICKER_WS = None
                    log.warning("KiteTicker connection closed: %s", _reason)
                    closed.set()

                def on_error(_ws, _code, _reason):
                    global TICKER_CONNECTED, TICKER_WS
                    TICKER_CONNECTED = False
                    TICKER_WS = None
                    log.error("KiteTicker error: %s", _reason)
                    closed.set()

                ticker.on_connect = on_connect
                ticker.on_ticks = on_ticks
                ticker.on_close = on_close
                ticker.on_error = on_error

                # IMPORTANT: threaded=True avoids Twisted signal handler issues on Render.
                ticker.connect(threaded=True)

                # IMPORTANT: wait here so we don't spawn infinite tickers.
                closed.wait()
                time.sleep(2)

            except Exception:
                TICKER_CONNECTED = False
                log.exception("KiteTicker stopped; retrying in 5 seconds")
                time.sleep(5)

    threading.Thread(target=run, name="kite-ticker", daemon=True).start()

# ----------------------------
# Fast mode symbol selection / rotation
# ----------------------------

def _fast_symbol_candidates(include_fallback: bool = True) -> list[str]:
    candidates = []
    with DATA_LOCK:
        items = list(SYMBOL_TO_TOKEN.items())
        tick_state = dict(TICK_STATE)
    for symbol, token in items:
        tick = tick_state.get(token) or {}
        ltp = _as_float(tick.get("ltp"))
        ohlc = tick.get("ohlc") if isinstance(tick.get("ohlc"), dict) else {}
        open_price = _as_float(ohlc.get("open"))
        volume = _as_float(tick.get("volume")) or 0.0
        if not ltp or not open_price:
            continue
        change = abs((ltp - open_price) / open_price * 100.0)
        candidates.append((change, volume, symbol))

    candidates.sort(reverse=True)
    selected = [symbol for _, _, symbol in candidates[:FAST_SYMBOL_LIMIT]]

    if not include_fallback:
        return selected

    fallback = list(dict.fromkeys(SECTOR_DEFINITIONS.get("NIFTY_50", []) + list(ALL_SYMBOLS)))
    for symbol in fallback:
        if len(selected) >= FAST_SYMBOL_LIMIT:
            break
        if symbol in SYMBOL_TO_TOKEN and symbol not in selected:
            selected.append(symbol)
    return selected


def _select_fast_symbols() -> list[str]:
    deadline = time.time() + FAST_SELECTION_WAIT_SEC
    while time.time() < deadline:
        live_selected = _fast_symbol_candidates(include_fallback=False)
        if len(live_selected) >= FAST_SYMBOL_LIMIT or not market_is_open():
            break
        time.sleep(1)

    selected = _fast_symbol_candidates()
    with DATA_LOCK:
        DETAIL_SYMBOLS.clear()
        DETAIL_SYMBOLS.update(selected[:FAST_SYMBOL_LIMIT])
        selected_symbols = set(DETAIL_SYMBOLS)
    _set_ticker_modes(selected_symbols)

    log.info("Fast mode selected %s/%s symbols for detailed history", len(DETAIL_SYMBOLS), len(SYMBOL_TO_TOKEN))
    return list(DETAIL_SYMBOLS)


def _seed_symbol(symbol: str, token: int) -> None:
    if kite is None:
        return
    now = datetime.now(IST)
    try:
        five = kite.historical_data(
            instrument_token=token,
            from_date=now - timedelta(days=SEED_DAYS_5M),
            to_date=now,
            interval="5minute",
            continuous=False,
            oi=False,
        )
        time.sleep(HISTORY_SLEEP_SEC)

        daily = kite.historical_data(
            instrument_token=token,
            from_date=now - timedelta(days=SEED_DAYS_DAILY),
            to_date=now,
            interval="day",
            continuous=False,
            oi=False,
        )

        completed = _normalize_history(five)
        bucket = market_bucket(datetime.now(IST))
        if bucket is not None and not completed.empty:
            completed = completed[completed["date"] < bucket].reset_index(drop=True)
        with DATA_LOCK:
            # Seeding can finish after ticks have already started. Preserve
            # any locally closed candles (and the live partial builder) rather
            # than overwriting them with a slow network response.
            existing = HISTORY.get(token, {}).get("intraday")
            if existing is not None and not existing.empty:
                completed = merge_finished(completed, existing.to_dict("records"))
            HISTORY[token] = {"intraday": completed, "regular": _normalize_history(daily)}
    finally:
        time.sleep(HISTORY_SLEEP_SEC)


def _rotate_fast_symbols() -> None:
    global FAST_SEED_IN_PROGRESS
    if not FAST_MODE or not market_is_open() or not TICKER_CONNECTED:
        return

    selected = set(_fast_symbol_candidates())
    with DATA_LOCK:
        current = set(DETAIL_SYMBOLS)
    added = selected - current
    if not added:
        return

    _set_ticker_modes(selected)
    FAST_SEED_IN_PROGRESS = True
    rotation_errors = 0
    ready = set()

    try:
        for symbol in sorted(added):
            token = SYMBOL_TO_TOKEN.get(symbol)
            if not token:
                continue
            try:
                _seed_symbol(symbol, token)
                with DATA_LOCK:
                    if not HISTORY.get(token, {}).get("intraday", pd.DataFrame()).empty:
                        ready.add(symbol)
            except Exception:
                rotation_errors += 1
                log.exception("Fast rotation seed failed for %s", symbol)
    finally:
        with DATA_LOCK:
            DETAIL_SYMBOLS.clear()
            DETAIL_SYMBOLS.update((current & selected) | ready)
            active_symbols = set(DETAIL_SYMBOLS)
        _set_ticker_modes(active_symbols)
        FAST_SEED_IN_PROGRESS = False

    log.info(
        "Fast mode rotated: %s detailed symbols, %s new histories, %s errors",
        len(active_symbols),
        len(ready),
        rotation_errors,
    )


def _start_fast_rotation() -> None:
    global FAST_ROTATION_STARTED
    if not FAST_MODE or FAST_ROTATION_STARTED or FAST_RESELECT_SEC <= 0:
        return
    FAST_ROTATION_STARTED = True

    def run() -> None:
        while True:
            time.sleep(FAST_RESELECT_SEC)
            try:
                _rotate_fast_symbols()
            except Exception:
                log.exception("Fast mode rotation failed")

    threading.Thread(target=run, name="fast-rotation", daemon=True).start()


# ----------------------------
# Daily refresh + seeding
# ----------------------------

def _prepare_for_new_market_day(today: date) -> None:
    """Reset live ticks while retaining the previous-session scan cache during reseeding."""
    global LAST_TICK_TS, TOTAL_TICKS
    with DATA_LOCK:
        PRICE_HISTORY.clear()
        TICK_STATE.clear()
        CANDLE_BUILDERS.clear()
        LAST_CONFIRMED_CANDLE.clear()
        VOLUME_PROFILE_CACHE.clear()
        SCORE_HISTORY.clear()
        FUTURES_QUOTES.clear()
        LAST_TICK_TS = 0.0
        TOTAL_TICKS = 0
    log.info("Preparing fresh market session for %s", today.isoformat())


def _start_daily_refresh() -> None:
    global DAILY_REFRESH_STARTED
    with DAILY_REFRESH_START_LOCK:
        if DAILY_REFRESH_STARTED:
            return
        DAILY_REFRESH_STARTED = True

    def run() -> None:
        global DAILY_REFRESH_REQUESTED_DATE
        while True:
            now = datetime.now(IST)
            seeded_date = HISTORY_SEED_DATE
            if (
                now.weekday() < 5
                and now.time() >= PREMARKET_SEED_TIME
                and seeded_date is not None
                and seeded_date < now.date()
                and DAILY_REFRESH_REQUESTED_DATE != now.date()
                and not SEED_IN_PROGRESS
            ):
                DAILY_REFRESH_REQUESTED_DATE = now.date()
                _prepare_for_new_market_day(now.date())
                try:
                    _start_incremental_refresh()
                except Exception:
                    log.exception("New market-day history seed failed")
            time.sleep(30)

    threading.Thread(target=run, name="daily-refresh", daemon=True).start()


def _start_history_seed(force: bool = False) -> None:
    """
    Retry-safe seeding:
    - SEED_REQUESTED_DATE marks the running/queued seed.
    - HISTORY_SEED_DATE is only updated after a successful completion.
    """
    global HISTORY_CACHE_LOADED, SEED_IN_PROGRESS, SEED_REQUESTED_DATE

    if kite is None:
        return

    if HISTORY_CACHE_LOADED and not force:
        log.info("Using persisted history cache; skipping redundant startup seed")
        return

    today = datetime.now(IST).date()

    if SEED_IN_PROGRESS or SEED_REQUESTED_DATE == today:
        log.info("Skipping duplicate seed request for %s", today.isoformat())
        return

    if force:
        # Force reseed even if cache was loaded.
        HISTORY_CACHE_LOADED = False

    SEED_REQUESTED_DATE = today
    SEED_PROGRESS.update({"done": 0, "total": 0, "errors": 0})
    SEED_IN_PROGRESS = True

    if FAST_MODE:
        selected_symbols = _select_fast_symbols()
    else:
        selected_symbols = list(SYMBOL_TO_TOKEN)
        with DATA_LOCK:
            DETAIL_SYMBOLS.clear()
            DETAIL_SYMBOLS.update(selected_symbols)

    tokens = sorted((token, symbol) for symbol, token in SYMBOL_TO_TOKEN.items() if symbol in selected_symbols)
    SEED_PROGRESS["total"] = len(tokens)

    def run() -> None:
        global HISTORY_CACHE_LOADED, SEED_IN_PROGRESS, HISTORY_SEED_DATE, SEED_REQUESTED_DATE
        seed_date = today
        try:
            for token, symbol in tokens:
                try:
                    for attempt in range(3):
                        try:
                            _seed_symbol(symbol, token)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            time.sleep(2 * (attempt + 1))
                except Exception:
                    SEED_PROGRESS["errors"] += 1
                    log.exception("History seed failed for %s after retries", symbol)
                finally:
                    SEED_PROGRESS["done"] += 1
        finally:
            SEED_IN_PROGRESS = False

            success = (SEED_PROGRESS["errors"] == 0 and SEED_PROGRESS["done"] == SEED_PROGRESS["total"])
            if success:
                HISTORY_SEED_DATE = seed_date
                _save_history_cache(seed_date)
                HISTORY_CACHE_LOADED = True
            else:
                HISTORY_CACHE_LOADED = False
                SEED_REQUESTED_DATE = None

            _start_fast_rotation()
            if success:
                _start_gap_recovery()

    threading.Thread(target=run, name="history-seed", daemon=True).start()


def _kite_history_datetime(value: Any) -> datetime:
    """Return a native Python datetime in IST for the Kite historical API.

    IMPORTANT: pykiteconnect checks ``type(x) == datetime.datetime`` rather
    than ``isinstance(x, datetime)``. A pandas Timestamp is passed through
    unformatted, including its ``+05:30`` timezone suffix, which Kite rejects
    with ``InputException: invalid from date``. Strip the timezone after
    converting to IST so Kite receives YYYY-MM-DD HH:MM:SS every time.
    """
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("Historical recovery date is missing")
    stamp = stamp.tz_localize(IST) if stamp.tzinfo is None else stamp.tz_convert(IST)
    return stamp.to_pydatetime().replace(tzinfo=None)


def _completed_history_cutoff(now: datetime) -> datetime:
    """Last possible *completed* NSE 5m boundary, respecting opening/close.

    The market calendar is not consulted; NSE holidays simply return no new
    candles. Weekends and pre-09:20 requests use the previous weekday close.
    """
    now_ist = now.replace(tzinfo=IST) if now.tzinfo is None else now.astimezone(IST)
    candidate = now_ist
    if candidate.weekday() >= 5 or candidate.time() < dtime(9, 20):
        candidate = candidate - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate.replace(hour=15, minute=30, second=0, microsecond=0)
    if candidate.time() >= dtime(15, 30):
        return candidate.replace(hour=15, minute=30, second=0, microsecond=0)
    return candidate.replace(minute=candidate.minute - candidate.minute % 5, second=0, microsecond=0)


def _recover_history(symbol: str, token: int, now: datetime, daily: bool = False) -> None:
    if kite is None:
        return
    with DATA_LOCK:
        existing = HISTORY.get(token, {})
        older = existing.get("intraday")
        daily_frame = existing.get("regular")

    end_of_completed = _completed_history_cutoff(now)
    if older is not None and not older.empty:
        latest = _kite_history_datetime(older.iloc[-1]["date"])
        # Completed last candle already covers the available session. Avoid
        # refetching the same 5m bars on each startup after market close.
        need_intraday = latest + timedelta(minutes=5) < _kite_history_datetime(end_of_completed)
        start_time = latest - timedelta(minutes=5)
    else:
        need_intraday = True
        start_time = _kite_history_datetime(now) - timedelta(days=SEED_DAYS_5M)
    start_time = max(start_time, _kite_history_datetime(end_of_completed) - timedelta(days=59))

    if need_intraday and start_time < _kite_history_datetime(end_of_completed):
        # Kite must receive native datetime, not pandas Timestamp.
        rows = kite.historical_data(
            token, _kite_history_datetime(start_time), _kite_history_datetime(end_of_completed),
            "5minute", continuous=False, oi=False,
        )
        additional = _normalize_history(rows)
        if not additional.empty:
            boundary = pd.Timestamp(end_of_completed)
            additional = additional[additional["date"] + pd.Timedelta(minutes=5) <= boundary]
            with DATA_LOCK:
                frame = HISTORY.setdefault(token, {}).get("intraday")
                HISTORY[token]["intraday"] = merge_finished(frame, additional.to_dict("records"))
    time.sleep(HISTORY_SLEEP_SEC)

    if daily:
        if daily_frame is not None and not daily_frame.empty:
            beginning = _kite_history_datetime(daily_frame.iloc[-1]["date"]) - timedelta(days=2)
        else:
            beginning = _kite_history_datetime(now) - timedelta(days=SEED_DAYS_DAILY)
        end_daily = _kite_history_datetime(now)
        if beginning < end_daily:
            rows = kite.historical_data(
                token, _kite_history_datetime(beginning), end_daily, "day",
                continuous=False, oi=False,
            )
            additional = _normalize_history(rows)
            if not additional.empty:
                with DATA_LOCK:
                    history = HISTORY.setdefault(token, {})
                    history["regular"] = merge_finished(
                        history.get("regular"), additional.to_dict("records"), max_rows=180,
                    )
        time.sleep(HISTORY_SLEEP_SEC)


def _start_gap_recovery(daily: bool = False) -> None:
    global RECOVERY_STARTED
    with RECOVERY_LOCK:
        if RECOVERY_STARTED or SEED_IN_PROGRESS or kite is None:
            return
        RECOVERY_STARTED = True
    def run() -> None:
        global RECOVERY_STARTED, HISTORY_SEED_DATE, HISTORY_CACHE_LOADED, DAILY_REFRESH_REQUESTED_DATE
        now = datetime.now(IST)
        errors = 0
        try:
            for symbol, token in list(SYMBOL_TO_TOKEN.items()):
                try:
                    with DATA_LOCK:
                        data = HISTORY.get(token, {}).get("intraday")
                    if data is None or data.empty:
                        errors += 1
                        continue  # initial seed owns these symbols; do not mark recovery complete
                    if daily or (now - data.iloc[-1]["date"]).total_seconds() >= 600:
                        _recover_history(symbol, token, datetime.now(IST), daily)
                except Exception:
                    errors += 1
                    if errors <= 3:
                        log.exception("Gap-recovery failed for %s", symbol)
                    else:
                        log.debug("Further gap-recovery error for %s", symbol, exc_info=True)
            if errors == 0:
                HISTORY_SEED_DATE = now.date()
                HISTORY_CACHE_LOADED = True
                _save_history_cache(now.date())
            else:
                log.warning("Gap recovery finished with %s errors; will retry", errors)
                DAILY_REFRESH_REQUESTED_DATE = None
        finally:
            RECOVERY_STARTED = False
    threading.Thread(target=run, name="gap-recovery", daemon=True).start()


def _start_incremental_refresh() -> None:
    _start_gap_recovery(daily=True)


# ----------------------------
# Indicators
# ----------------------------

def _ema(values: pd.Series, period: int = 21) -> Optional[float]:
    if values.empty:
        return None
    return _as_float(values.ewm(span=period, adjust=False, min_periods=1).mean().iloc[-1])


def _rsi(values: pd.Series, period: int = 14) -> Optional[float]:
    if len(values) < 3:
        return None
    delta = values.diff()
    gains = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=1).mean()
    losses = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=1).mean()
    last_loss = float(losses.iloc[-1])
    if last_loss <= 1e-12:
        return 100.0 if float(gains.iloc[-1]) > 0 else 50.0
    result = 100.0 - (100.0 / (1.0 + float(gains.iloc[-1]) / last_loss))
    return max(0.0, min(100.0, result))


def _adx(frame: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(frame) < 4:
        return None
    high, low, close = frame["high"], frame["low"], frame["close"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr = true_range.ewm(alpha=1 / period, adjust=False, min_periods=1).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=1).mean() / (atr + 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=1).mean() / (atr + 1e-9)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
    return max(0.0, min(100.0, float(dx.ewm(alpha=1 / period, adjust=False, min_periods=1).mean().iloc[-1])))


# ----------------------------
# Row building
# ----------------------------

def _history_state(token: int, timeframe: str) -> Optional[tuple[pd.DataFrame, float, float, dict]]:
    with DATA_LOCK:
        frame = HISTORY.get(token, {}).get(timeframe)
        tick = dict(TICK_STATE.get(token) or {})
    if frame is None or frame.empty:
        return None

    last = frame.iloc[-1]
    tick_ltp = _as_float(tick.get("ltp")) if tick.get("day") == datetime.now(IST).date() else None
    ltp = tick_ltp or _as_float(last.get("close"))
    volume = _as_float(tick.get("volume")) or _as_float(last.get("volume")) or 0.0
    ohlc = tick.get("ohlc") if isinstance(tick.get("ohlc"), dict) else {}

    if not ohlc:
        if timeframe == "intraday":
            latest_date = last["date"].date()
            session = frame[frame["date"].dt.date == latest_date]
            if not session.empty:
                ohlc = {
                    "open": session.iloc[0]["open"],
                    "high": session["high"].max(),
                    "low": session["low"].min(),
                    "close": session.iloc[-1]["close"],
                }
                if tick_ltp is None:
                    volume = float(session["volume"].sum())
        else:
            ohlc = {"open": last.get("open"), "high": last.get("high"), "low": last.get("low"), "close": last.get("close")}

    if ltp is None:
        return None

    return frame.copy(), float(ltp), float(volume), ohlc


def _volume_ratio(token: int, timeframe: str, volume: float, now: datetime) -> float:
    with DATA_LOCK:
        daily = HISTORY.get(token, {}).get("regular")
    if daily is None or daily.empty:
        return 1.0

    daily = daily[daily["volume"] > 0]
    if daily.empty:
        return 1.0

    if timeframe == "regular":
        baseline = float(daily["volume"].tail(61).head(60).mean())
        return max(0.0, volume / (baseline + 1e-9))

    baseline = float(daily["volume"].tail(20).mean())
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)

    if not market_is_open(now) or not _has_current_session_data(now):
        elapsed = 375.0
    else:
        elapsed = (now - market_open).total_seconds() / 60.0
        elapsed = max(1.0, min(375.0, elapsed))

    expected = baseline * (elapsed / 375.0)
    return max(0.0, volume / (expected + 1e-9))


def _trend_features(frame: pd.DataFrame, ltp: float, now: datetime) -> dict:
    """Return session VWAP and 5m/15m EMA alignment for regime detection."""
    empty = {"vwapGap": None, "emaTrend5": None, "emaTrend15": None}
    if frame.empty or "date" not in frame:
        return empty

    current = frame[frame["date"].dt.date == now.date()].copy()
    if current.empty:
        if market_is_open(now):
            # Yesterday's VWAP is not today's VWAP. Until the first partial
            # candle arrives, these intraday trend signals are unavailable.
            return empty
        latest_date = frame["date"].dt.date.max()
        current = frame[frame["date"].dt.date == latest_date].copy()
    if current.empty:
        return empty

    current = current.sort_values("date")
    closes = pd.to_numeric(current["close"], errors="coerce").dropna().astype(float)
    if closes.empty or not ltp:
        return empty
    closes.iloc[-1] = float(ltp)

    ema_fast = _ema(closes, 9)
    ema_slow = _ema(closes, 21)
    trend5 = ((ema_fast - ema_slow) / ltp * 100.0) if ema_fast is not None and ema_slow is not None else None

    buckets = current.assign(_bucket=current["date"].dt.floor("15min")).groupby("_bucket", sort=True)["close"].last()
    buckets = pd.to_numeric(buckets, errors="coerce").dropna().astype(float)
    if not buckets.empty:
        buckets.iloc[-1] = float(ltp)
    ema15_fast = _ema(buckets, 3) if len(buckets) >= 2 else None
    ema15_slow = _ema(buckets, 8) if len(buckets) >= 2 else None
    trend15 = ((ema15_fast - ema15_slow) / ltp * 100.0) if ema15_fast is not None and ema15_slow is not None else None

    volume = pd.to_numeric(current["volume"], errors="coerce").fillna(0.0).clip(lower=0.0)
    typical = (pd.to_numeric(current["high"], errors="coerce") + pd.to_numeric(current["low"], errors="coerce") + pd.to_numeric(current["close"], errors="coerce")) / 3.0
    total_volume = float(volume.sum())
    vwap = float((typical * volume).sum() / total_volume) if total_volume > 0 else None
    vwap_gap = ((ltp - vwap) / vwap * 100.0) if vwap and vwap > 0 else None

    return {"vwapGap": vwap_gap, "emaTrend5": trend5, "emaTrend15": trend15}


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _daily_atr_percent(token: int) -> float:
    """Return a prior-session daily ATR percentage without using today's candle."""
    with DATA_LOCK:
        daily = HISTORY.get(token, {}).get("regular")
    if daily is None or daily.empty:
        return 1.0

    stats = daily[daily["volume"] > 0].copy()
    if "date" in stats:
        stats = stats[stats["date"].dt.date < datetime.now(IST).date()]
    if stats.empty:
        return 1.0

    previous_close = stats["close"].shift(1)
    true_range = pd.concat(
        [stats["high"] - stats["low"], (stats["high"] - previous_close).abs(), (stats["low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_percent = (true_range / stats["close"].replace(0, pd.NA) * 100.0).dropna().tail(20)
    value = float(atr_percent.mean()) if not atr_percent.empty else 1.0
    return value if math.isfinite(value) and value > 0 else 1.0


def _intraday_volume_ratio(token: int, frame: pd.DataFrame, volume: float, now: datetime) -> float:
    """Cache slot cumulative-volume medians; don't group 45d of candles every 8s."""
    if frame.empty:
        return 1.0
    day = now.date()
    historical = frame[frame["date"].dt.date < day]
    if historical.empty:
        return 1.0
    latest_day = historical.iloc[-1]["date"].date()
    key = (day, latest_day, len(historical))
    with DATA_LOCK:
        stored = VOLUME_PROFILE_CACHE.get(token)
    if stored is None or stored[0] != key:
        sessions = []
        for _, series in list(historical.groupby(historical["date"].dt.date))[-30:]:
            series = series.sort_values("date")
            slot_numbers = (series["date"].dt.hour * 60 + series["date"].dt.minute - 555) // 5
            slot_volume = {int(slot): float(vol) for slot, vol in zip(slot_numbers, series["volume"]) if 0 <= slot < 75}
            cumulative = 0.0
            session_profile = {}
            for slot in range(75):
                if slot in slot_volume:
                    cumulative += max(0.0, slot_volume[slot])
                    session_profile[slot] = cumulative
            sessions.append(session_profile)
        medians = {}
        for slot in range(75):
            values = [session[slot] for session in sessions if slot in session and session[slot] > 0]
            if len(values) >= 5:
                medians[slot] = float(pd.Series(values).median())
        with DATA_LOCK:
            VOLUME_PROFILE_CACHE[token] = (key, medians)
    else:
        medians = stored[1]
    slot = max(0, min(74, int((now.hour * 60 + now.minute - 555) // 5)))
    baseline = medians.get(slot)
    if baseline and market_is_open(now):
        # The historical slot baseline is measured at the END of its 5m
        # candle. A live quote at 09:16 should instead be compared with the
        # expected progress through that candle, not all of 09:15-09:20.
        bucket = market_bucket(now)
        if bucket is not None:
            fraction = max(0.08, min(1.0, (now - bucket).total_seconds() / 300.0))
            previous = medians.get(slot - 1, 0.0) if slot > 0 else 0.0
            if previous is not None:
                baseline = float(previous) + (float(baseline) - float(previous)) * fraction
    return round(max(0., volume / baseline), 2) if baseline and baseline > 0 else 1.0


def _live_candles(token: int, now: datetime) -> list[dict]:
    with DATA_LOCK:
        frame = HISTORY.get(token, {}).get("intraday")
        builder = CANDLE_BUILDERS.get(token)
        partial = builder.partial() if builder else None
    finished = []
    if frame is not None and not frame.empty:
        today = frame[frame["date"].dt.date == now.date()].tail(4)
        finished = [{"open": float(r.open), "high": float(r.high), "low": float(r.low),
                     "close": float(r.close), "volume": float(r.volume)} for r in today.itertuples()]
    if partial and partial["date"].date() == now.date():
        finished.append({key: partial[key] for key in ("open", "high", "low", "close", "volume")})
    return finished[-4:]


def _session_trend_quality(frame: pd.DataFrame, ltp: float, change: float, now: datetime, live_candles: Optional[list[dict]] = None) -> float:
    if frame.empty:
        return 1.0
    today = frame[frame["date"].dt.date == now.date()]
    if today.empty and not live_candles:
        latest_date = frame.iloc[-1]["date"].date()
        today = frame[frame["date"].dt.date == latest_date]

    expected_direction = 1.0 if change >= 0 else -1.0
    quality = 1.0

    if not today.empty:
        values = [_as_float(today.iloc[0]["open"])] + [_as_float(v) for v in today["close"].tolist()]
        values = [v for v in values if v is not None and v > 0]
        if len(values) >= 2:
            values.append(ltp)
            meaningful = []
            for previous, current in zip(values, values[1:]):
                move = (current - previous) / previous * 100.0 * expected_direction
                meaningful.append(move >= 0.02)
            continuity = sum(meaningful) / len(meaningful) if meaningful else 0.0
            quality = max(0.05, continuity * continuity)

    if live_candles and len(live_candles) >= 2:
        live_moves = [
            ((c["close"] - c["open"]) / c["open"] * 100.0) * expected_direction
            for c in live_candles[-3:]
            if c.get("open")
        ]
        if live_moves:
            live_cont = sum(m >= 0.02 for m in live_moves) / len(live_moves)
            quality = min(quality, max(0.05, live_cont * live_cont))

    return quality


def _volume_confirmation(frame: pd.DataFrame, expected_direction: float, now: datetime, live_candles: Optional[list[dict]] = None) -> float:
    if frame.empty:
        return 1.0

    intraday = frame[frame["volume"] > 0]
    today = intraday[intraday["date"].dt.date == now.date()]
    session_date = now.date()

    if today.empty and not live_candles and not intraday.empty:
        session_date = intraday.iloc[-1]["date"].date()
        today = intraday[intraday["date"].dt.date == session_date]

    history = intraday[intraday["date"].dt.date < session_date]
    baseline_source = history["volume"].tail(120) if not history.empty else intraday["volume"].iloc[:-3]
    baseline = float(baseline_source.median()) if not baseline_source.empty else 0.0
    if baseline <= 0:
        return 1.0

    if live_candles and any((c.get("volume") or 0) > 0 for c in live_candles):
        recent = live_candles[-3:]
        moves = [
            ((c["close"] - c["open"]) / c["open"] * 100.0) * expected_direction
            for c in recent
            if c.get("open")
        ]
        volumes = [float(c.get("volume") or 0.0) for c in recent]
        if moves and volumes:
            directional_rate = sum((m >= 0.02) and (v >= baseline * 0.80) for m, v in zip(moves, volumes)) / len(recent)
            recent_volume_ratio = (sum(volumes) / len(volumes)) / baseline
        else:
            directional_rate = 0.0
            recent_volume_ratio = 1.0
    elif today.empty:
        return 1.0
    else:
        recent = today.tail(3)
        moves = ((recent["close"] - recent["open"]) / recent["open"] * 100.0) * expected_direction
        confirmed = (moves >= 0.02) & (recent["volume"] >= baseline * 0.80)
        directional_rate = float(confirmed.mean()) if len(confirmed) else 0.0
        recent_volume_ratio = float(recent["volume"].mean()) / baseline

    activity = min(1.0, recent_volume_ratio / 1.20)
    return max(0.10, min(1.0, 0.20 + directional_rate * 0.55 + activity * 0.25))


def _sparkline(prices: List[float], positive: bool) -> str:
    values = prices[-5:]
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    spread = max(high - low, 1e-9)
    coords = " ".join(f"{i * 18},{24 - ((v - low) / spread) * 19:.1f}" for i, v in enumerate(values))
    color = "#0d9b73" if positive else "#d44e57"
    return f'<svg class="spark" viewBox="0 0 72 26" aria-label="Five candle trend"><polyline fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="{coords}"></polyline></svg>'


def _rfactor(token: int, timeframe: str, ltp: float, volume: float, high: float, low: float, change: float) -> float:
    # Matches your comment: "dashboard_clean.py" style.
    with DATA_LOCK:
        daily = HISTORY.get(token, {}).get("regular")
    if daily is None or daily.empty:
        return 0.0

    stats = daily[daily["volume"] > 0].copy()
    if stats.empty:
        return 0.0

    if "date" in stats:
        stats = stats[stats["date"].dt.date < datetime.now(IST).date()]
    if stats.empty:
        return 0.0

    stats["change"] = stats["close"].pct_change() * 100.0
    stats = stats.tail(20)

    close = float(ltp or 0.0)
    vol = float(volume or 0.0)
    if vol <= 0 or close <= 0 or stats.empty:
        return 0.0

    avg_vol = float(stats["volume"].mean())
    avg_range = float((stats["high"] - stats["low"]).mean())
    avg_move = float(stats["change"].abs().mean())
    baselines = (avg_vol, avg_range, avg_move)
    if not all(math.isfinite(v) and v > 0 for v in baselines):
        return 0.0

    rvol = vol / avg_vol
    range_factor = (high - low) / avg_range
    move_factor = abs(change) / avg_move
    raw = (rvol ** 0.55) * (range_factor ** 0.30) * (move_factor ** 0.15)

    position = (close - low) / ((high - low) + 1e-9)
    freshness = position ** 3 if change >= 0 else (1.0 - position) ** 3

    if (high - low) / close * 100.0 < 0.60:
        raw *= 0.12

    raw *= max(freshness, 0.001)
    return round(3.5 * math.log1p(max(raw, 0.0)), 2)


def _advanced_score_components(row: dict, relative_strength: float = 0.5) -> dict:
    """Actual weighted score contributions (point sum equals reported score)."""
    direction = 1.0 if float(row.get("direction") or 1.0) > 0 else -1.0
    change = abs(float(row.get("change") or 0.0))
    atr_percent = max(float(row.get("atrPercent") or 1.0), 0.25)
    r = _clip(change / atr_percent / 2.0)
    ratio = max(float(row.get("timeVolumeRatio") or 1.0), 0.05)
    vr = _clip(0.5 + 0.20 * math.log(ratio, 2.0))
    v = 0.55 * vr + 0.45 * _clip(float(row.get("volumeConfirm") or 0.5))
    recent = _clip(0.5 + 0.25 * direction * float(row.get("recent") or 0))
    cont = 0.60 * _clip(float(row.get("trendQuality") or 0.5)) + 0.40 * recent
    adx = _clip((float(row.get("adx") or 10.0) - 10.0) / 30.0)
    trend = 0.60 * adx + 0.40 * _clip(0.5 + direction * float(row.get("ema") or 0.0) / 5.0)
    flow_delta = row.get("depthImbalance")
    flow = 0.5 if flow_delta is None else _clip(0.5 + 0.40 * direction * float(flow_delta))
    rf = _clip(float(row.get("rfactor") or 0) / 4.)
    return {"price": 25 * r, "volume": 20 * v, "continuation": 15 * cont,
            "trend": 15 * trend, "relative": 10 * _clip(relative_strength),
            "restingDepth": 10 * flow, "rfactor": 5 * rf}


def _advanced_score(row: dict, relative_strength: float = 0.5) -> float:
    return round(sum(_advanced_score_components(row, relative_strength).values()), 4)


def _apply_advanced_scores(rows: List[dict]) -> List[dict]:
    """Add cross-sectional sector and market relative strength before ranking."""
    if not rows:
        return rows

    market_mean = sum(float(row.get("change") or 0.0) for row in rows) / len(rows)
    sector_values: Dict[str, List[float]] = {}
    for row in rows:
        sector_values.setdefault(str(row.get("sector") or "UNKNOWN"), []).append(float(row.get("change") or 0.0))
    sector_means = {sector: sum(values) / len(values) for sector, values in sector_values.items() if values}
    dispersion = sum(abs(float(row.get("change") or 0.0) - market_mean) for row in rows) / len(rows)
    scale = max(0.25, dispersion * 1.5)

    for row in rows:
        direction = 1.0 if float(row.get("direction") or 1.0) > 0 else -1.0
        change = float(row.get("change") or 0.0)
        sector_mean = sector_means.get(str(row.get("sector") or "UNKNOWN"), market_mean)
        sector_edge = direction * (change - sector_mean)
        market_edge = direction * (change - market_mean)
        relative_strength = 0.60 * _clip(0.5 + 0.25 * sector_edge / scale) + 0.40 * _clip(0.5 + 0.25 * market_edge / scale)
        row["sectorRelative"] = round(sector_edge, 2)
        row["marketRelative"] = round(market_edge, 2)
        row["score"] = _advanced_score(row, relative_strength)
        row["scoreDrivers"] = {key: round(value, 2) for key, value in _advanced_score_components(row, relative_strength).items()}
    return rows


def _build_row(symbol: str, sector: str, timeframe: str) -> Optional[dict]:
    token = SYMBOL_TO_TOKEN.get(symbol)
    if not token:
        return None

    hs = _history_state(token, timeframe)
    if hs is None:
        return None

    frame, ltp, volume, ohlc = hs
    if timeframe == "intraday":
        with DATA_LOCK:
            builder = CANDLE_BUILDERS.get(token)
            partial = builder.partial() if builder else None
        if partial and partial["date"].date() == datetime.now(IST).date():
            frame = merge_finished(frame, [partial])
    open_price = _as_float(ohlc.get("open")) or _as_float(frame.iloc[-1]["open"])
    day_high = _as_float(ohlc.get("high")) or _as_float(frame.iloc[-1]["high"])
    day_low = _as_float(ohlc.get("low")) or _as_float(frame.iloc[-1]["low"])
    if not open_price or not day_high or not day_low:
        return None

    if timeframe == "regular" and len(frame) >= 2:
        previous_close = _as_float(frame.iloc[-2]["close"]) or open_price
        change = (ltp - previous_close) / (previous_close + 1e-9) * 100.0
    else:
        change = (ltp - open_price) / (open_price + 1e-9) * 100.0

    closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
    close_values = closes.tolist()
    if timeframe == "intraday" and not frame.empty and market_bucket(datetime.now(IST)) == frame.iloc[-1]["date"]:
        close_values[-1] = ltp
    else:
        close_values.append(ltp)
    indicator_closes = pd.Series(close_values, dtype="float64")

    indicator_frame = frame[["high", "low", "close"]].copy()
    live_row = indicator_frame.iloc[-1].copy()
    live_row["high"] = max(float(live_row["high"]), ltp)
    live_row["low"] = min(float(live_row["low"]), ltp)
    live_row["close"] = ltp
    indicator_frame = pd.concat([indicator_frame.iloc[:-1], pd.DataFrame([live_row])], ignore_index=True)

    rsi = _rsi(indicator_closes)
    adx = _adx(indicator_frame)
    ema = _ema(indicator_closes)
    if rsi is None or adx is None or ema is None or ema <= 0:
        return None

    now = datetime.now(IST)
    trend_features = _trend_features(frame, ltp, now)
    daily_pace_ratio = _volume_ratio(token, timeframe, volume, now)
    atr_percent = _daily_atr_percent(token)
    time_volume_ratio = _intraday_volume_ratio(token, frame, volume, now) if timeframe == "intraday" else daily_pace_ratio
    ratio = time_volume_ratio if timeframe == "intraday" else daily_pace_ratio
    baseline_ready = (timeframe != "intraday" or bool(VOLUME_PROFILE_CACHE.get(token, (None, {}))[1]))
    ema_gap = (ltp - ema) / ema * 100.0

    live_candles = _live_candles(token, now) if timeframe == "intraday" else []
    recent_change = 0.0
    if len(live_candles) >= 2:
        recent_base = live_candles[max(0, len(live_candles) - 3)]["open"]
        recent_change = (ltp - recent_base) / recent_base * 100.0
    elif len(close_values) >= 4 and close_values[-4]:
        recent_change = (ltp - close_values[-4]) / close_values[-4] * 100.0

    expected_direction = 1.0 if change >= 0 else -1.0
    trend_quality = _session_trend_quality(frame, ltp, change, now, live_candles) if timeframe == "intraday" else 1.0
    volume_quality = _volume_confirmation(frame, expected_direction, now, live_candles) if timeframe == "intraday" else 1.0

    flow_values = [c.get("flow_delta") for c in live_candles[-3:] if c.get("flow_delta") is not None]
    latest_depth = (TICK_STATE.get(token) or {}).get("depth_imbalance")
    buy_sell_delta = latest_depth  # resting-depth imbalance, NOT executed buy/sell volume

    rfactor = _rfactor(token, timeframe, ltp, volume, day_high, day_low, change)
    continuation_quality = max(0.05, min(1.0, trend_quality * volume_quality))

    volatility = (
        "high" if abs(change) >= 2.5 or abs(ema_gap) >= 2.5
        else "medium" if abs(change) >= 1.0 or abs(ema_gap) >= 1.2
        else "low"
    )
    positive = change >= 0

    row = {
        "symbol": symbol,
        "display": symbol,
        "ltp": round(ltp, 2),
        "sector": sector,
        "direction": 1 if positive else -1,
        "change": round(change, 2),
        "recent": round(recent_change, 2),
        "trendQuality": round(trend_quality, 2),
        "volumeConfirm": round(volume_quality, 2),
        "continuation": round(continuation_quality, 2),
        "depthImbalance": round(buy_sell_delta, 3) if buy_sell_delta is not None else None,
        "buySellDelta": None,  # deprecated: do not mislabel resting depth as executed flow
        "volume": round((ratio - 1.0) * 100.0, 2),
        "ratio": round(ratio, 2),
        "timeVolumeRatio": round(time_volume_ratio, 2),
        "volumeBaselineReady": baseline_ready,
        "dailyPaceRatio": round(daily_pace_ratio, 2),
        "vwapGap": round(trend_features["vwapGap"], 2) if trend_features["vwapGap"] is not None else None,
        "emaTrend5": round(trend_features["emaTrend5"], 3) if trend_features["emaTrend5"] is not None else None,
        "emaTrend15": round(trend_features["emaTrend15"], 3) if trend_features["emaTrend15"] is not None else None,
        "atrPercent": round(atr_percent, 2),
        "rsi": round(rsi, 1),
        "adx": round(adx, 1),
        "ema": round(ema_gap, 2),
        "score": 0.0,
        "rfactor": rfactor,
        "volatility": volatility,
        "rank": 0,
        "spark": _sparkline(close_values, positive),
        "isIndex": False,
    }
    row["score"] = _advanced_score(row)
    row["asOf"] = datetime.fromtimestamp((TICK_STATE.get(token) or {}).get("ts") or 0, IST).isoformat() if (TICK_STATE.get(token) or {}).get("ts") else None
    row["fresh"] = bool(row["asOf"] and time.time() - TICK_STATE[token]["ts"] <= TICK_STALE_SEC)
    row["tradedVolume"] = round(float(TICK_STATE.get(token, {}).get("volume") or 0)) if row["asOf"] else None
    row["scoreStatus"] = "provisional" if timeframe == "intraday" and market_is_open(now) else "historical"
    row["scoreSource"] = "history_and_ticks"
    if timeframe == "intraday":
        today = frame[frame["date"].dt.date == now.date()]
        row.update(one_way_metrics(today, row["direction"]))
        prior_daily = HISTORY.get(token, {}).get("regular")
        prior = prior_daily[prior_daily["date"].dt.date < now.date()] if prior_daily is not None and not prior_daily.empty else None
        previous_day = prior.iloc[-1].to_dict() if prior is not None and not prior.empty else None
        # Only closed candles establish breakout reference levels.
        closed = today.iloc[:-1] if not today.empty and market_bucket(now) and today.iloc[-1]["date"] == market_bucket(now) else today
        row["alerts"] = breakout_signals(closed, previous_day, ltp, time_volume_ratio)
        row["momentum5"] = round((ltp / float(frame.iloc[-2]["close"]) - 1) * 100, 2) if len(frame) > 1 else None
        row["momentum15"] = round((ltp / float(frame.iloc[-4]["close"]) - 1) * 100, 2) if len(frame) > 3 else None
        row["momentum30"] = round((ltp / float(frame.iloc[-7]["close"]) - 1) * 100, 2) if len(frame) > 6 else None

    return row


def _last_closed_five_minute(token: int, now: datetime) -> Optional[dict]:
    """Completed 5m candle only; never treat the live builder as confirmed."""
    with DATA_LOCK:
        latest = LAST_CONFIRMED_CANDLE.get(token)
        if not latest or latest["date"].date() != now.date():
            frame = HISTORY.get(token, {}).get("intraday")
            if frame is None or frame.empty:
                return None
            today = frame[frame["date"].dt.date == now.date()]
            if today.empty:
                return None
            closed = today[today["date"] + pd.Timedelta(minutes=5) <= now]
            if closed.empty:
                return None
            latest = closed.iloc[-1].to_dict()
            LAST_CONFIRMED_CANDLE[token] = latest
        latest = dict(latest)
    if latest["date"] + timedelta(minutes=5) > now:
        return None
    open_price, close_price = float(latest["open"]), float(latest["close"])
    momentum_pct = (close_price / open_price - 1) * 100 if open_price > 0 else None
    return {
        "start": latest["date"].isoformat(),
        "end": (latest["date"] + pd.Timedelta(minutes=5)).isoformat(),
        "close": round(close_price, 2),
        "momentumPct": round(momentum_pct, 2) if momentum_pct is not None else None,
        # Stable, price-only candle strength (0-100); NOT the composite
        # multi-indicator live score. Only closed prices enter this metric.
        "priceMomentumScore": round(min(100., abs(momentum_pct) * 16.), 1) if momentum_pct is not None else None,
    }


def _live_quote_row(symbol: str, sector: str, now: datetime) -> Optional[dict]:
    """Immediate quote-first row, even while the history seed is incomplete.

    A provisional tick-only score is intentionally NOT passed off as the full
    baseline-dependent composite score. Missing RSI, ADX and volume ratio
    remain null until real historical inputs arrive.
    """
    token = SYMBOL_TO_TOKEN.get(symbol)
    if not token:
        return None
    with DATA_LOCK:
        tick = dict(TICK_STATE.get(token) or {})
        builder = CANDLE_BUILDERS.get(token)
        partial = builder.partial() if builder else None
    if tick.get("day") != now.date() or not market_is_open(now):
        return None
    ltp = _as_float(tick.get("ltp"))
    if ltp is None or ltp <= 0:
        return None
    ohlc = tick.get("ohlc") or {}
    open_price = _as_float(ohlc.get("open"))
    reference = open_price if open_price and open_price > 0 else _as_float(ohlc.get("close"))
    if not reference or reference <= 0:
        return None
    change = (ltp / reference - 1.0) * 100.0
    candle_open = _as_float(partial.get("open")) if partial else None
    current_5m = (ltp / candle_open - 1.0) * 100.0 if candle_open and candle_open > 0 else 0.0
    # Quote-only stopgap: direction and price movement, no invented volume
    # normalization or RSI. Full composite replaces this when history loads.
    provisional_score = min(100.0, max(0.0, abs(change) * 16.0 + abs(current_5m) * 12.0))
    tick_time = float(tick.get("ts") or 0)
    positive = change >= 0
    return {
        "symbol": symbol, "display": symbol, "sector": sector,
        "ltp": round(ltp, 2), "change": round(change, 2),
        "tradedVolume": int(float(tick.get("volume") or 0)),
        "changeBasis": "open" if open_price and open_price > 0 else "previous_close",
        "direction": 1 if positive else -1, "score": round(provisional_score, 2),
        "scoreStatus": "provisional", "scoreSource": "live_quote_only",
        "ratio": None, "volume": None, "timeVolumeRatio": None,
        "volumeBaselineReady": False, "rsi": None, "adx": None,
        "rfactor": None, "ema": None, "vwapGap": None, "emaTrend5": None,
        "emaTrend15": None, "spark": "", "rank": 0, "isIndex": False,
        "volatility": "high" if abs(change) >= 2.5 else "medium" if abs(change) >= 1 else "low",
        "asOf": datetime.fromtimestamp(tick_time, IST).isoformat() if tick_time else None,
        "fresh": bool(tick_time and time.time() - tick_time <= TICK_STALE_SEC),
        "lastCompleted5m": _last_closed_five_minute(token, now),
    }


def _quote_first_rows(timeframe: str, universe: str, sector: str, cached: List[dict]) -> List[dict]:
    """Update LTP/% change directly from Kite ticks, bypassing slow scoring."""
    if universe != "stocks" or not market_is_open():
        return cached
    now = datetime.now(IST)
    # Historical cache rows without today's Kite quotes must NOT be mixed into
    # the opening-bell leaderboards and mistaken for current market movers.
    with DATA_LOCK:
        active_symbols = {
            TOKEN_TO_SYMBOL[token]
            for token, tick in TICK_STATE.items()
            if token in TOKEN_TO_SYMBOL and tick.get("day") == now.date()
        }
    by_symbol = {row["symbol"]: row for row in cached if row["symbol"] in active_symbols}
    symbols = SECTOR_DEFINITIONS.get(sector, []) if sector != "ALL" else ALL_SYMBOLS
    for symbol in dict.fromkeys(symbols):
        quote = _live_quote_row(symbol, PRIMARY_SECTOR.get(symbol, "OTHER"), now)
        if quote is None:
            continue
        row = by_symbol.get(symbol)
        if row is None:
            by_symbol[symbol] = quote
            continue
        # The expensive indicators retain their computed values, while
        # high-priority price fields are fresh at each API request.
        for key in ("ltp", "change", "direction", "changeBasis", "asOf", "fresh", "lastCompleted5m", "tradedVolume"):
            row[key] = quote[key]
        row["scoreStatus"] = "provisional" if timeframe == "intraday" else "historical"
        if row.get("scoreSource") == "live_quote_only":
            row["score"] = quote["score"]
        # A previous-session historical row may be visible during today's
        # background seed; never let it masquerade as an entirely live score.
    # Baseline-free rows deliberately retain their quote-only score; running
    # the historical composite here would fabricate unavailable indicators.
    return _rank(list(by_symbol.values()))


INDEX_GROUPS = {
    "NIFTY 50": SECTOR_DEFINITIONS["NIFTY_50"],
    "BANK NIFTY": SECTOR_DEFINITIONS["BANK"] + SECTOR_DEFINITIONS["PSUBANK"],
    "NIFTY IT": SECTOR_DEFINITIONS["IT"],
    "NIFTY AUTO": SECTOR_DEFINITIONS["AUTO"],
    "NIFTY METAL": SECTOR_DEFINITIONS["METAL"],
    "NIFTY PHARMA": SECTOR_DEFINITIONS["PHARMA"],
    "NIFTY ENERGY": SECTOR_DEFINITIONS["ENERGY"],
    "NIFTY REALTY": SECTOR_DEFINITIONS["REALTY"],
}


def _aggregate_index(name: str, rows: List[dict]) -> Optional[dict]:
    if not rows:
        return None
    weights = [max(float(row.get("ratio") or 1.0), 0.1) for row in rows]
    total_weight = sum(weights)

    def average(key: str) -> float:
        return sum(float(row.get(key) or 0.0) * w for row, w in zip(rows, weights)) / total_weight

    change = average("change")
    ltp = average("ltp")
    ratio = average("ratio")
    ema = average("ema")
    score = average("score")
    vwap_gap = average("vwapGap")
    ema_trend5 = average("emaTrend5")
    ema_trend15 = average("emaTrend15")

    strongest = max(rows, key=lambda row: float(row.get("score") or 0.0))
    volatility = "high" if abs(change) >= 1.8 else "medium" if abs(change) >= 0.8 else "low"

    return {
        "symbol": name,
        "display": name,
        "ltp": round(ltp, 2),
        "sector": "INDEX",
        "direction": 1 if change >= 0 else -1,
        "change": round(change, 2),
        "volume": round((ratio - 1.0) * 100.0, 2),
        "ratio": round(ratio, 2),
        "vwapGap": round(vwap_gap, 2),
        "emaTrend5": round(ema_trend5, 3),
        "emaTrend15": round(ema_trend15, 3),
        "rsi": round(average("rsi"), 1),
        "adx": round(average("adx"), 1),
        "ema": round(ema, 2),
        "score": round(score, 4),
        "rfactor": round(average("rfactor"), 2),
        "volatility": volatility,
        "rank": 0,
        "spark": strongest.get("spark", ""),
        "isIndex": True,
    }


def _directional_rank(rows: List[dict], score_key: str) -> List[dict]:
    ranked = sorted(
        rows,
        key=lambda row: (
            float(row.get(score_key) or 0.0),
            abs(float(row.get("change") or 0.0)),
            str(row.get("symbol") or ""),
        ),
        reverse=True,
    )
    for position, row in enumerate(ranked, start=1):
        row["rank"] = position
    return ranked


def _rank(rows: List[dict]) -> List[dict]:
    rows[:] = _directional_rank(rows, "score")
    for row in rows:
        row["_scan_score"] = row.get("score")
    return rows


def build_rows(timeframe: str, universe: str, sector: str) -> List[dict]:
    sector = sector.upper()
    with DATA_LOCK:
        detail_symbols = set(DETAIL_SYMBOLS)

    if universe == "index":
        rows = []
        for name, symbols in INDEX_GROUPS.items():
            selected = [s for s in dict.fromkeys(symbols) if (not FAST_MODE or s in detail_symbols)]
            children = _apply_advanced_scores([row for row in (_build_row(s, "INDEX", timeframe) for s in selected) if row])
            aggregate = _aggregate_index(name, [r for r in children if r])
            if aggregate:
                rows.append(aggregate)
        return _rank(_apply_advanced_scores(rows))

    symbols = list(dict.fromkeys(SECTOR_DEFINITIONS.get(sector, []))) if sector != "ALL" else list(ALL_SYMBOLS)
    if FAST_MODE:
        symbols = [symbol for symbol in symbols if symbol in detail_symbols]

    rows = [_build_row(symbol, PRIMARY_SECTOR.get(symbol, "OTHER"), timeframe) for symbol in symbols]
    return _rank(_apply_advanced_scores([row for row in rows if row]))


def _rows_from_cache(timeframe: str, universe: str, sector: str) -> List[dict]:
    """Return a request-specific view without recalculating indicators."""
    with SCAN_CACHE_LOCK:
        rows = [dict(row) for row in SCAN_CACHE.get(timeframe, {}).get(universe, [])]
    if universe == "stocks" and sector != "ALL":
        rows = [row for row in rows if row.get("symbol") in SECTOR_DEFINITIONS.get(sector, [])]
    rows = _quote_first_rows(timeframe, universe, sector, rows)
    rows = _directional_rank(rows, "_scan_score")
    for row in rows:
        row.pop("_scan_score", None)
    return rows


def build_sector_flow(rows: Optional[List[dict]] = None) -> List[dict]:
    score_by_symbol = {str(row.get("symbol")): row for row in (rows or []) if row.get("symbol")}
    now = datetime.now(IST)
    with DATA_LOCK:
        ticks = {symbol: dict(TICK_STATE.get(token) or {}) for symbol, token in SYMBOL_TO_TOKEN.items()}
    results = []
    for sector, symbols in INDUSTRY_GROUPS.items():
        valid = []
        for symbol in dict.fromkeys(symbols):
            tick = ticks.get(symbol) or {}
            ltp = _as_float(tick.get("ltp"))
            open_price = _as_float((tick.get("ohlc") or {}).get("open"))
            if not (ltp and open_price and tick.get("day") == now.date()):
                continue
            change = (ltp / open_price - 1) * 100
            row = score_by_symbol.get(symbol) or {}
            valid.append((symbol, change, row))
        if not valid:
            continue
        ratios = [float(row["timeVolumeRatio"]) for _, _, row in valid if row.get("timeVolumeRatio") is not None]
        scores = [float(row["score"]) * (1 if change >= 0 else -1) for _, change, row in valid if row.get("score") is not None]
        results.append({"name": sector, "mean": round(sum(x[1] for x in valid) / len(valid), 2),
                        "volume_ratio_mean": round(sum(ratios) / len(ratios), 2) if ratios else None,
                        "dirRScore": round(sum(scores) / len(scores), 2) if scores else None,
                        "count": len(valid), "total": len(set(symbols)), "up": sum(x[1] > 0 for x in valid),
                        "down": sum(x[1] < 0 for x in valid),
                        "leaders": sum(abs(x[1]) >= 1 and float(x[2].get("timeVolumeRatio") or 0) >= 1.5 for x in valid)})
    return sorted(results, key=lambda item: item["mean"], reverse=True)


def _refresh_scan_cache() -> None:
    global SCAN_CACHE_UPDATED_AT, LAST_CACHE_SAVE_AT
    _flush_completed_candles(datetime.now(IST))
    snapshots = {}
    for timeframe in ("intraday", "regular"):
        snapshots[timeframe] = {
            "stocks": build_rows(timeframe, "stocks", "ALL"),
            "index": build_rows(timeframe, "index", "ALL"),
        }
    # Store one snapshot per minute for momentum acceleration; no lookahead.
    snapshot_time = time.time()
    for row in snapshots["intraday"]["stocks"]:
        name = row["symbol"]
        samples = SCORE_HISTORY.setdefault(name, deque(maxlen=45))
        if not samples or snapshot_time - samples[-1][0] >= 58:
            samples.append((snapshot_time, float(row["score"])))
        for minutes in (5, 15, 30):
            older = [score for ts, score in samples if ts <= snapshot_time - minutes * 60]
            row[f"scoreDelta{minutes}"] = round(float(row["score"]) - older[-1], 1) if older else None
        delta = row.get("scoreDelta5")
        row["momentumState"] = "accelerating" if delta is not None and delta >= 4 else ("fading" if delta is not None and delta <= -4 else "steady")
    sector_flow = build_sector_flow(snapshots["intraday"]["stocks"])

    with SCAN_CACHE_LOCK:
        for timeframe, universes in snapshots.items():
            SCAN_CACHE[timeframe]["stocks"] = universes["stocks"]
            SCAN_CACHE[timeframe]["index"] = universes["index"]
        SECTOR_FLOW_CACHE.clear()
        SECTOR_FLOW_CACHE.extend(sector_flow)
        SCAN_CACHE_UPDATED_AT = time.time()
    # Persist completed 5m candles periodically; at restart only gaps need API recovery.
    if HISTORY_SEED_DATE and time.time() - LAST_CACHE_SAVE_AT >= 300 and not RECOVERY_STARTED and not SEED_IN_PROGRESS:
        LAST_CACHE_SAVE_AT = time.time()
        threading.Thread(target=_save_history_cache, args=(HISTORY_SEED_DATE,), name="cache-save", daemon=True).start()


def _start_scan_compute() -> None:
    global SCAN_COMPUTE_STARTED
    with SCAN_COMPUTE_START_LOCK:
        if SCAN_COMPUTE_STARTED:
            return
        SCAN_COMPUTE_STARTED = True

    def run() -> None:
        while True:
            started = time.monotonic()
            try:
                _refresh_scan_cache()
            except Exception:
                log.exception("Background scan cache refresh failed")
            elapsed = time.monotonic() - started
            time.sleep(max(0.1, SCAN_COMPUTE_EVERY_SEC - elapsed))

    threading.Thread(target=run, name="scan-compute", daemon=True).start()


# ----------------------------
# Live initialization (lazy, safe under Gunicorn)
# ----------------------------

def initialize_live() -> None:
    """Start live services once per process."""
    global LIVE_INITIALIZED
    with LIVE_INIT_LOCK:
        if LIVE_INITIALIZED:
            return
        LIVE_INITIALIZED = True

    _start_scan_compute()

    try:
        load_instruments()
        if kite is not None and SYMBOL_TO_TOKEN:
            # Always subscribe before any potentially slow history/bootstrap
            # work. Quotes must not wait for an entire universe to be seeded.
            _start_ticker()
            if not _load_history_cache():
                _start_history_seed(force=False)
            elif HISTORY_SEED_DATE and HISTORY_SEED_DATE < datetime.now(IST).date():
                _start_incremental_refresh()
            if FAST_MODE:
                with DATA_LOCK:
                    DETAIL_SYMBOLS.update(_fast_symbol_candidates()[:FAST_SYMBOL_LIMIT])
            else:
                with DATA_LOCK:
                    DETAIL_SYMBOLS.update(SYMBOL_TO_TOKEN)
        else:
            log.warning("Live init: instruments not loaded (missing credentials or symbols).")
    except Exception:
        log.exception("Live market startup failed; serving UI without live feed")
    finally:
        _start_daily_refresh()


def ensure_live_started() -> None:
    # Avoid starting background threads at import-time; start on first request.
    if not LIVE_INITIALIZED:
        initialize_live()


# ----------------------------
# Routes
# ----------------------------

@app.get("/")
def index():
    ensure_live_started()
    return send_file(BASE_DIR / "intraday-momentum-scanner.html")


@app.post("/api/access/login")
def access_login():
    if membership.enabled():
        return jsonify({"error": "google_membership_required"}), 403
    ensure_live_started()
    payload = request.get_json(silent=True) or {}
    phone = normalize_access_number(payload.get("phone"))
    session_id = clean_env(str(payload.get("session_id", "")))

    if not phone or not session_id:
        return jsonify({"ok": False, "error": "invalid_request"}), 400

    allowlist = allowed_access_numbers()
    if phone not in allowlist:
        return jsonify({"ok": False, "error": "not_allowed"}), 403

    now = time.time()
    _prune_sessions(now)

    with ACCESS_SESSION_LOCK:
        current = ACTIVE_ACCESS_SESSIONS.get(phone)
        if current and current.get("session_id") != session_id:
            return jsonify({"ok": False, "error": "already_logged_in"}), 409
        ACTIVE_ACCESS_SESSIONS[phone] = {"session_id": session_id, "ts": now}

    return jsonify({"ok": True})


@app.post("/api/access/logout")
def access_logout():
    if membership.enabled():
        return jsonify({"error": "google_membership_required"}), 403
    ensure_live_started()
    payload = request.get_json(silent=True) or {}
    phone = normalize_access_number(payload.get("phone"))
    session_id = clean_env(str(payload.get("session_id", "")))
    with ACCESS_SESSION_LOCK:
        record = ACTIVE_ACCESS_SESSIONS.get(phone)
        if record and record.get("session_id") == session_id:
            ACTIVE_ACCESS_SESSIONS.pop(phone, None)
    return jsonify({"ok": True})


@app.get("/api/health")
def health():
    ensure_live_started()
    status, live = _feed_status()
    return jsonify(
        {
            "status": status,
            "live": live,
            "market_open": market_is_open(),
            "seed": dict(SEED_PROGRESS),
            "symbols": len(SYMBOL_TO_TOKEN),
            "fast_mode": FAST_MODE,
            "detail_symbols": len(DETAIL_SYMBOLS),
            "ticks": TOTAL_TICKS,
            "last_tick": datetime.fromtimestamp(LAST_TICK_TS, IST).isoformat() if LAST_TICK_TS else None,
            "cache_ready": bool(SCAN_CACHE_UPDATED_AT),
            "futures_enabled": ENABLE_FUTURES_OI,
            "authentication": ("google_login_only" if membership.free_mode() else "google_razorpay_test" if membership.test_mode() else "google_paid_membership") if membership.enabled() else "numbers_txt_allowlist",
            "cache_updated_at": datetime.fromtimestamp(SCAN_CACHE_UPDATED_AT, IST).isoformat() if SCAN_CACHE_UPDATED_AT else None,
            "history_cache_loaded": HISTORY_CACHE_LOADED,
            "invalid_kite_token": INVALID_KITE_TOKEN,
            "history_seed_date": HISTORY_SEED_DATE.isoformat() if HISTORY_SEED_DATE else None,
            "seed_requested_date": SEED_REQUESTED_DATE.isoformat() if SEED_REQUESTED_DATE else None,
        }
    )


# Google authentication is opt-in via MEMBERSHIP_AUTH_MODE=google_free (login only)
# or google_test (simulated payments), or google (live, explicitly allowed). Phone sessions never bypass.
def _request_is_authorized() -> bool:
    if membership.enabled():
        try:
            return membership.has_paid_access(membership.bearer_token())
        except membership.MembershipError:
            return False
    phone = normalize_access_number(request.args.get("access_phone"))
    session_id = clean_env(request.args.get("access_session_id", ""))
    return access_session_is_active(phone, session_id)


@app.get("/api/membership/config")
def membership_config():
    response = jsonify(membership.config_payload())
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get("/api/membership/me")
def membership_me():
    if not membership.enabled():
        return jsonify({'error': 'membership_mode_disabled'}), 404
    try:
        user, profile = membership.member_status(membership.bearer_token())
        response = jsonify({'user': user, 'membership': {
            'status': profile['status'] if profile else 'pending',
            'paid_at': profile.get('paid_at') if profile else None,
        }})
        response.headers['Cache-Control'] = 'no-store'
        return response
    except membership.MembershipError as error:
        return jsonify({'error': error.code}), error.status


# Compatible Standard Checkout endpoint names; both reuse the membership flow.
@app.post("/api/create-order")
@app.post("/api/membership/order")
def membership_order():
    if not membership.paid_mode():
        return jsonify({'error': 'membership_mode_disabled'}), 404
    try:
        user = membership.get_google_user(membership.bearer_token())
        payload = request.get_json(silent=True)
        membership.validate_order_request(payload if payload is not None else {})
        response = jsonify(membership.create_order(user))
        response.headers['Cache-Control'] = 'no-store'
        return response
    except membership.MembershipError as error:
        return jsonify({'error': error.code}), error.status


@app.post("/api/verify-payment")
@app.post("/api/membership/verify")
def membership_verify():
    if not membership.paid_mode():
        return jsonify({'error': 'membership_mode_disabled'}), 404
    try:
        user = membership.get_google_user(membership.bearer_token())
        response = jsonify(membership.verify_checkout(user, request.get_json(silent=True)))
        response.headers['Cache-Control'] = 'no-store'
        return response
    except membership.MembershipError as error:
        return jsonify({'error': error.code}), error.status


@app.post("/api/membership/webhook")
def membership_webhook():
    if not membership.paid_mode():
        return jsonify({'error': 'membership_mode_disabled'}), 404
    try:
        result = membership.handle_webhook(request.get_data(), request.headers.get('X-Razorpay-Signature', ''))
        return jsonify(result)
    except membership.MembershipError as error:
        return jsonify({'error': error.code}), error.status


@app.get("/api/scan")
def scan():
    ensure_live_started()

    # Auth (required)
    if not _request_is_authorized():
        return jsonify({"error": "access_required"}), 403

    timeframe = request.args.get("type", "intraday").lower()
    universe = request.args.get("universe", "stocks").lower()
    sector = request.args.get("sector", "all").upper()

    if timeframe not in {"intraday", "regular"}:
        return jsonify({"error": "type must be intraday or regular"}), 400
    if universe not in {"stocks", "index"}:
        return jsonify({"error": "universe must be stocks or index"}), 400
    if sector not in SECTOR_DEFINITIONS and sector != "ALL":
        sector = "ALL"

    # Limit (bandwidth control)
    try:
        limit = int(request.args.get("limit", str(DEFAULT_SCAN_LIMIT)))
    except ValueError:
        limit = DEFAULT_SCAN_LIMIT
    limit = max(1, min(MAX_SCAN_LIMIT, limit))

    with SCAN_CACHE_LOCK:
        cache_updated_at = SCAN_CACHE_UPDATED_AT
        sector_flow = [dict(item) for item in SECTOR_FLOW_CACHE]

    # ETag / 304 (saves bandwidth if client revalidates)
    etag = f'W/"scan-{timeframe}-{universe}-{sector}-{limit}-{int(cache_updated_at)}"'
    # The expensive score cache refreshes every few seconds, but LTP and
    # cumulative volume now come directly from ticks at request time. A 304
    # based only on the score-cache timestamp would hide those live changes.
    if not market_is_open() and request.headers.get("If-None-Match") == etag and cache_updated_at:
        resp = Response(status=304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        return resp

    rows = _rows_from_cache(timeframe, universe, sector)[:limit]
    status, live = _feed_status()

    payload = {
        "live": live,
        "status": status,
        "market_open": market_is_open(),
        "quote_first": True,
        "score_phase": "live_provisional_with_closed_5m_snapshots",
        "updated_at": datetime.fromtimestamp(cache_updated_at, IST).strftime("%H:%M:%S IST") if cache_updated_at else None,
        "seed": dict(SEED_PROGRESS),
        "fast_mode": FAST_MODE,
        "universe_size": len(SYMBOL_TO_TOKEN),
        "detail_symbols": len(DETAIL_SYMBOLS),
        "nifty_index": _official_nifty_quote(),
        "sector_flow": sector_flow,
        "ticks": TOTAL_TICKS,
        "last_tick": datetime.fromtimestamp(LAST_TICK_TS, IST).isoformat() if LAST_TICK_TS else None,
        "rows": rows,
    }

    resp = jsonify(payload)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "no-store" if market_is_open() else "private, max-age=0, must-revalidate"
    return resp


@app.get("/api/stock/<symbol>/candles")
def stock_candles(symbol: str):
    if not _request_is_authorized():
        return jsonify({"error": "access_required"}), 403
    token = SYMBOL_TO_TOKEN.get(symbol.upper())
    if not token:
        return jsonify({"error": "unknown_symbol"}), 404
    with DATA_LOCK:
        frame = HISTORY.get(token, {}).get("intraday")
        builder = CANDLE_BUILDERS.get(token)
        partial = builder.partial() if builder else None
    if frame is None or frame.empty:
        return jsonify({"symbol": symbol, "candles": [], "status": "waiting_for_history"})
    day = datetime.now(IST).date()
    if not (frame["date"].dt.date == day).any():
        day = frame.iloc[-1]["date"].date()
    rows = frame[frame["date"].dt.date == day].tail(75).to_dict("records")
    if partial and partial["date"].date() == day:
        rows.append(partial)
    candles = [{"time": row["date"].isoformat(), **{k: round(float(row[k]), 3) for k in ("open", "high", "low", "close", "volume")},
                "partial": partial is not None and row["date"] == partial["date"]} for row in rows]
    return jsonify({"symbol": symbol.upper(), "candles": candles})


@app.get("/api/replay")
def replay():
    if not _request_is_authorized():
        return jsonify({"error": "access_required"}), 403
    try:
        day = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400
    if day > datetime.now(IST).date():
        return jsonify({"error": "future_date"}), 400
    symbol = request.args.get("symbol", "").upper()
    if symbol not in SYMBOL_TO_TOKEN:
        return jsonify({"error": "unknown_symbol"}), 404
    with DATA_LOCK:
        frame = HISTORY.get(SYMBOL_TO_TOKEN[symbol], {}).get("intraday")
        frame = frame.copy() if frame is not None else pd.DataFrame()
    return jsonify({"symbol": symbol, "date": day.isoformat(), "mode": "simplified_historical_replay",
                    "limitations": "5m OHLCV replay, not a reconstruction of tick order flow or the full live score",
                    "rows": replay_session(frame, day)})


@app.get("/api/futures")
def futures():
    if not _request_is_authorized():
        return jsonify({"error": "access_required"}), 403
    with DATA_LOCK:
        quotes = dict(FUTURES_QUOTES)
        symbols = dict(FUTURES_TOKENS)
    rows = []
    for token, record in quotes.items():
        base_oi, base_price = record["base_oi"], record["base_price"]
        oi_pct = (record["oi"] / base_oi - 1) * 100 if base_oi else 0
        price_pct = (record["ltp"] / base_price - 1) * 100 if base_price else 0
        classification = ("Long build-up" if oi_pct > 0 and price_pct > 0 else
                          "Short build-up" if oi_pct > 0 and price_pct < 0 else
                          "Short covering" if oi_pct < 0 and price_pct > 0 else
                          "Long unwinding" if oi_pct < 0 and price_pct < 0 else "Neutral")
        rows.append({"symbol": symbols.get(token), "ltp": record["ltp"], "priceChange": round(price_pct, 2),
                     "oiChange": round(oi_pct, 2), "classification": classification,
                     "baseline": "first observed tick this market session", "asOf": datetime.fromtimestamp(record["ts"], IST).isoformat()})
    return jsonify({"enabled": ENABLE_FUTURES_OI, "rows": sorted(rows, key=lambda row: abs(row["oiChange"]), reverse=True)})


# ----------------------------
# Local dev entrypoint
# ----------------------------

def start() -> None:
    initialize_live()
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)


if __name__ == "__main__":
    start()
