"""Pure, testable market-data features for the NSE intraday scanner.

A finished 5-minute candle is never overwritten by an unfinished candle.
All times are exchange-local Asia/Kolkata; prices/volumes are observations, not trades attributed to a buyer.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)


def market_bucket(dt: datetime) -> Optional[datetime]:
    dt = dt.astimezone(IST)
    start = dt.replace(hour=9, minute=15, second=0, microsecond=0)
    offset = int((dt - start).total_seconds())
    if offset < 0 or offset >= 375 * 60 or dt.weekday() >= 5:
        return None
    return start + timedelta(minutes=5 * (offset // 300))


@dataclass
class FiveMinuteBuilder:
    start: Optional[datetime] = None
    candle: Optional[dict] = None
    previous_total: Optional[float] = None

    def ingest(self, dt: datetime, price: float, total_volume: float, baseline_volume: float = 0) -> Optional[dict]:
        bucket = market_bucket(dt)
        if bucket is None or not math.isfinite(price) or price <= 0:
            return None
        total_volume = max(0., float(total_volume))
        completed = None
        if self.start is not None and bucket < self.start:
            return None  # Out-of-order quote must not alter closed candles.
        if bucket != self.start:
            if self.candle:
                completed = {"date": self.start, **self.candle}
            self.start = bucket
            self.candle = {"open": price, "high": price, "low": price, "close": price, "volume": 0.}
        else:
            self.candle["high"] = max(self.candle["high"], price)
            self.candle["low"] = min(self.candle["low"], price)
            self.candle["close"] = price
        # Kite volume_traded is cumulative volume for the trading session. First sample
        # derives a baseline from completed historical bars (0 near market open).
        before = self.previous_total if self.previous_total is not None else max(0., baseline_volume)
        increment = max(0., total_volume - before) if total_volume >= before else 0.
        self.candle["volume"] += increment
        self.previous_total = total_volume
        return completed

    def partial(self) -> Optional[dict]:
        return {"date": self.start, **self.candle} if self.candle else None


def merge_finished(frame: pd.DataFrame, rows: list[dict], max_rows: int = 4500) -> pd.DataFrame:
    if not rows:
        return frame
    additions = pd.DataFrame(rows)
    merged = pd.concat([frame, additions], ignore_index=True) if frame is not None and not frame.empty else additions
    merged["date"] = pd.to_datetime(merged["date"], utc=True).dt.tz_convert(IST)
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date").tail(max_rows)
    return merged.reset_index(drop=True)


def cumulative_slot_ratio(frame: pd.DataFrame, total_volume: float, now: datetime, sessions: int = 30) -> Optional[float]:
    """Median prior-session cumulative volume at the same 5m trading slot.

    No use of the current session in the baseline. Missing historical sessions return
    None rather than a deceptively neutral value.
    """
    if frame is None or frame.empty:
        return None
    reference_day = now.astimezone(IST).date()
    prior = frame[(frame["date"].dt.date < reference_day) & (frame["volume"] >= 0)].copy()
    if prior.empty:
        return None
    prior["slot"] = (prior["date"].dt.hour * 60 + prior["date"].dt.minute - 555) // 5
    prior = prior[(prior["slot"] >= 0) & (prior["slot"] < 75)]
    slot = min(74, max(0, int((now.astimezone(IST).hour * 60 + now.astimezone(IST).minute - 555) // 5)))
    values = []
    for _, group in list(prior.groupby(prior["date"].dt.date))[-sessions:]:
        group = group[group["slot"] <= slot]
        if len(group) and len(group) >= max(1, slot // 2):
            values.append(float(group["volume"].sum()))
    if len(values) < 5:
        return None
    baseline = float(pd.Series(values).median())
    return max(0., total_volume / baseline) if baseline > 0 else None


def one_way_metrics(frame: pd.DataFrame, direction: int, candles: int = 6) -> dict:
    if frame is None or len(frame) < 3:
        return {"oneWay": False, "oneWayStrength": 0., "pullbackPercent": None}
    sample = frame.tail(candles)
    moves = sample["close"].diff().dropna().astype(float).tolist()
    agreeing = sum(direction * move > 0 for move in moves)
    strength = agreeing / len(moves) if moves else 0.
    prices = sample["close"].astype(float).to_list()
    if direction > 0:
        peak = max(prices)
        pullback = (peak - prices[-1]) / peak * 100 if peak else 0.
    else:
        floor = min(prices)
        pullback = (prices[-1] - floor) / floor * 100 if floor else 0.
    move_pct = direction * (prices[-1] / prices[0] - 1) * 100 if prices[0] else 0.
    return {"oneWay": strength >= 0.75 and pullback <= 0.35 and move_pct >= 0.4,
            "oneWayStrength": round(strength * 100, 1), "pullbackPercent": round(pullback, 2)}


def breakout_signals(today: pd.DataFrame, previous_day: Optional[dict], ltp: float, ratio: Optional[float]) -> list[str]:
    if today is None or today.empty or ratio is None or ratio < 1.25:
        return []
    signals = []
    # Confirm relative to the previous completed 5m close, so a long-standing
    # level crossing is not repeatedly reported as a new signal.
    previous_close = float(today.iloc[-1]["close"])
    if len(today) >= 3:
        opening = today.head(3)
        upper, lower = float(opening["high"].max()), float(opening["low"].min())
        if previous_close <= upper < ltp:
            signals.append("15m ORB ↑")
        if previous_close >= lower > ltp:
            signals.append("15m ORB ↓")
    if previous_day:
        upper, lower = previous_day.get("high"), previous_day.get("low")
        if upper and previous_close <= upper < ltp:
            signals.append("Previous high ↑")
        if lower and previous_close >= lower > ltp:
            signals.append("Previous low ↓")
    return signals


def replay_session(frame: pd.DataFrame, day: date) -> list[dict]:
    """No-lookahead, simplified 5-minute replay; future returns are evaluation labels only."""
    if frame is None or frame.empty:
        return []
    session = frame[frame["date"].dt.date == day].sort_values("date").reset_index(drop=True)
    if len(session) < 4:
        return []
    out = []
    opening = float(session.iloc[0]["open"])
    for i in range(3, len(session)):
        past = session.iloc[:i + 1]
        close = float(past.iloc[-1]["close"])
        volumes = past["volume"].clip(lower=0)
        vwap = float(((past["high"] + past["low"] + past["close"]) / 3 * volumes).sum() / volumes.sum()) if volumes.sum() else None
        change = (close / opening - 1) * 100 if opening else 0
        mom15 = (close / float(past.iloc[-4]["close"]) - 1) * 100
        direction = 1 if change >= 0 else -1
        score = min(100., abs(change) * 12 + abs(mom15) * 10 + one_way_metrics(past, direction)["oneWayStrength"] * .25)
        row = {"time": past.iloc[-1]["date"].isoformat(), "close": round(close, 2), "change": round(change, 2),
               "momentum15": round(mom15, 2), "replayScore": round(score, 1),
               "vwap": round(vwap, 2) if vwap else None}
        for forward in (1, 3, 6):
            future = float(session.iloc[i + forward]["close"]) if i + forward < len(session) else None
            row[f"forward{forward * 5}m"] = round((future / close - 1) * 100, 2) if future and close else None
        out.append(row)
    return out
