"""Standalone 09:20+ IST continuation screen. Does not modify existing scanner.

ALL readings use only completed 5-minute OHLCV candles. Scores are *candidate
quality*, not predictions or trade recommendations. No live partial candles.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date, time, timedelta
from statistics import median
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo
import math

IST = ZoneInfo('Asia/Kolkata')
MIN_SESSIONS = 5
FULL_CANDLES = 9
FIRST_CANDLE_TIME = time(9, 20)
MAX_BASELINE_SESSIONS = 30
MIN_TURNOVER_RUPEES = 10_000_000  # >= 1 crore by the cutoff


def cutoff_for(now: datetime) -> datetime:
    """Local 5-minute boundary; current running candle is always excluded."""
    local = now.astimezone(IST)
    floored = local.replace(minute=(local.minute // 5) * 5, second=0, microsecond=0)
    return min(floored, floored.replace(hour=15, minute=30))


def _number(value) -> float:
    try:
        val = float(value)
        return val if math.isfinite(val) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _clip(val: float) -> float:
    return round(min(100.0, max(0.0, val)), 2)


def _normalise(raw: Sequence[dict], cutoff: datetime) -> list[dict]:
    """Verify candle end <= cutoff; suppress duplicate/out-of-session bars."""
    result = {}
    for candle in raw:
        when = candle.get('date')
        if isinstance(when, str):
            try:
                when = datetime.fromisoformat(when)
            except ValueError:
                continue
        if not isinstance(when, datetime):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)
        when = when.astimezone(IST)
        if not (time(9, 15) <= when.time() < time(15, 30)):
            continue
        if when + timedelta(minutes=5) > cutoff:
            continue
        price = _number(candle.get('close'))
        op = _number(candle.get('open'))
        high = _number(candle.get('high'))
        low = _number(candle.get('low'))
        vol = _number(candle.get('volume'))
        if price <= 0 or op <= 0 or high <= 0 or low <= 0 or vol < 0:
            continue
        result[when] = {'date': when, 'open': op, 'high': high, 'low': low,
                        'close': price, 'volume': vol}
    return [result[key] for key in sorted(result)]


def _first_n_session(candles: Sequence[dict], day: date, n: int) -> list[dict]:
    sessions = {c['date']: c for c in candles if c['date'].date() == day}
    anchor = datetime.combine(day, time(9, 15), tzinfo=IST)
    output = [sessions.get(anchor + timedelta(minutes=5*i)) for i in range(n)]
    return output if all(c is not None for c in output) else []


def _ema(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    # Seed from the first period mean rather than pretending missing candles are zero.
    avg = sum(values[:period]) / period
    factor = 2 / (period + 1)
    for value in values[period:]:
        avg = value * factor + avg * (1 - factor)
    return avg


def _rvol(all_candles: Sequence[dict], day: date, count: int, current_vol: float) -> tuple[float | None, int]:
    days = sorted({c['date'].date() for c in all_candles if c['date'].date() < day}, reverse=True)
    volumes = []
    for prev_day in days[:MAX_BASELINE_SESSIONS]:
        comparable = _first_n_session(all_candles, prev_day, count)
        if comparable:
            volumes.append(sum(c['volume'] for c in comparable))
    if len(volumes) < MIN_SESSIONS or median(volumes) <= 0:
        return None, len(volumes)
    return round(current_vol / median(volumes), 3), len(volumes)


def _direction_quality(session: Sequence[dict], history: Sequence[dict], direction: int, rvol: float) -> dict:
    op = session[0]['open']
    closes = [c['close'] for c in session]
    volumes = [c['volume'] for c in session]
    change = (closes[-1] / op - 1) * 100
    steps = [op] + closes
    path = sum(abs(b - a) for a, b in zip(steps, steps[1:]))
    efficiency = 100 * abs(closes[-1] - op) / path if path > 0 else 0.0
    total_volume = sum(volumes)
    confirming_volume = sum(c['volume'] for c in session if direction * (c['close']-c['open']) > 0)
    persistence = 100 * confirming_volume / total_volume if total_volume > 0 else 0.0
    # Directional higher-highs/higher-lows (or lower-highs/lower-lows).
    structure_pairs = [direction * (b[key] - a[key]) > 0
                       for a, b in zip(session, session[1:]) for key in ('high', 'low')]
    structure = 100 * sum(structure_pairs)/len(structure_pairs) if structure_pairs else 0.0
    close_positions = []
    for c in session:
        rng = c['high'] - c['low']
        close_position = (c['close'] - c['low']) / rng if rng > 0 else 0.5
        close_positions.append(close_position if direction > 0 else 1 - close_position)
    near_extreme = 100 * sum(close_positions)/len(close_positions)
    persistence_quality = _clip(0.45*persistence + 0.35*structure + 0.20*near_extreme)

    typical_vol_sum = sum((c['high'] + c['low'] + c['close'])/3 * c['volume'] for c in session)
    vwap = typical_vol_sum / total_volume if total_volume > 0 else None
    prev_volume = sum(c['volume'] for c in session[:-3])
    prev_sum = sum((c['high']+c['low']+c['close'])/3*c['volume'] for c in session[:-3])
    earlier_vwap = prev_sum / prev_volume if prev_volume > 0 else None
    closes_all = [c['close'] for c in history if c['date'] <= session[-1]['date']]
    e9, e21 = _ema(closes_all, 9), _ema(closes_all, 21)
    aligned = bool(vwap is not None and e9 is not None and e21 is not None and
                   direction*(closes[-1]-vwap)>0 and direction*(e9-e21)>0)
    alignment = _clip(
        35*(vwap is not None and direction*(closes[-1]-vwap)>0) +
        35*(e9 is not None and e21 is not None and direction*(e9-e21)>0) +
        20*(earlier_vwap is not None and vwap is not None and direction*(vwap-earlier_vwap)>0) +
        10*(e9 is not None and direction*(closes[-1]-e9)>0))
    opening_range = session[:6]  # 09:15–09:45; breakout possible only after the range completes.
    or_high = max(c['high'] for c in opening_range)
    or_low = min(c['low'] for c in opening_range)
    range_ready = len(session) >= 6
    breakout = ((closes[-1] > or_high if direction > 0 else closes[-1] < or_low)
                if len(session) > 6 else False)
    running_extreme = op
    reversal = 0.0
    for close in closes:
        if direction > 0:
            running_extreme = max(running_extreme, close)
            reversal = max(reversal, (running_extreme-close)/running_extreme*100)
        else:
            running_extreme = min(running_extreme, close)
            reversal = max(reversal, (close-running_extreme)/running_extreme*100)
    turnover = sum(((c['high']+c['low']+c['close'])/3)*c['volume'] for c in session)
    volume_score = _clip(100*(rvol/2.5))
    return dict(changePct=round(change, 2), efficiency=round(efficiency, 1),
                persistence=round(persistence, 1), structure=round(structure, 1),
                persistenceQuality=persistence_quality, vwap=round(vwap, 2) if vwap else None,
                ema9=round(e9, 2) if e9 else None, ema21=round(e21, 2) if e21 else None,
                alignmentScore=alignment, aligned=aligned, breakout=breakout, openingRangeReady=range_ready,
                orHigh=round(or_high,2), orLow=round(or_low,2),
                maxReversalPct=round(reversal, 2), turnover=round(turnover),
                volumeScore=volume_score)


def scan_continuation(histories: Mapping[str, Sequence[dict]], sectors: Mapping[str, Sequence[str]],
                      now: datetime) -> dict:
    """Rank early *developing* directions from 09:20 and full candidates at 10:00.

    A snapshot only consumes candles that have fully ended at/before cutoff.
    Before 10:00 the score is provisional; ORB, sufficient intraday structure,
    and all confirmation thresholds are not assumed to be available yet.
    """
    local = now.astimezone(IST)
    cutoff = cutoff_for(now)
    response = {'asOf': cutoff.strftime('%Y-%m-%d %H:%M IST'),
                'timeframe': '5m completed only', 'bullish': [], 'bearish': [],
                'noTradeCount': 0, 'eligibleCount': 0, 'scannedCount': len(histories),
                'status': 'ok', 'phase': 'collecting', 'completedCandles': 0,
                'niftyReference': 'NIFTY50 constituent equal-weight proxy',
                'minBaselineSessions': MIN_SESSIONS,
                'method': 'Trend efficiency 25%, persistence/structure 25%, VWAP/EMA 20%, RVOL 15%, relative strength 15%'}
    if local.weekday() >= 5 or local.time() > time(15, 30):
        response['status'] = 'market_closed'
        return response
    if local.time() < time(9, 15):
        response['status'] = 'pre_market'
        return response
    if cutoff.time() < FIRST_CANDLE_TIME:
        response['status'] = 'collecting_first_candle'
        return response

    day = cutoff.date()
    count = max(1, min(75, int((cutoff - datetime.combine(day, time(9, 15), tzinfo=IST)).total_seconds() // 300)))
    full = count >= FULL_CANDLES
    response['phase'] = 'confirmed_screen' if full else 'developing'
    response['completedCandles'] = count
    response['openingRangeReady'] = count >= 6
    base = []
    for symbol, candles in histories.items():
        prepared = _normalise(candles, cutoff)
        session = _first_n_session(prepared, day, count)
        if not session:
            continue
        # The 10:00 full screen still needs a real 21-candle EMA history;
        # developing views can operate with fewer completed bars.
        if full and len(prepared) < 21:
            continue
        cum_volume = sum(c['volume'] for c in session)
        rvol, baseline_sessions = _rvol(prepared, day, count, cum_volume)
        move = (session[-1]['close'] / session[0]['open'] - 1) * 100
        base.append({'symbol': symbol, 'session': session, 'history': prepared,
                     'move': move, 'rvol': rvol, 'baselineSessions': baseline_sessions})
    if not base:
        response['status'] = 'waiting_for_candles'
        return response

    sector_by_symbol = {}
    for name, constituents in sectors.items():
        if name != 'NIFTY_50':
            for symbol in constituents:
                sector_by_symbol.setdefault(symbol, name)
    moves = {entry['symbol']: entry['move'] for entry in base}
    nifty_moves = [moves[s] for s in sectors.get('NIFTY_50', []) if s in moves]
    nifty = sum(nifty_moves) / len(nifty_moves) if len(nifty_moves) >= 10 else None
    sector_returns = {}
    for name, symbols in sectors.items():
        group = [moves[s] for s in symbols if s in moves]
        if name != 'NIFTY_50' and len(group) >= 2:
            sector_returns[name] = sum(group) / len(group)
    response['benchmarkCoverage'] = len(nifty_moves)
    response['benchmarkReady'] = nifty is not None
    if nifty is None and full:
        response['status'] = 'waiting_for_benchmark'
        return response
    if nifty is not None:
        response['niftyProxyChangePct'] = round(nifty, 2)

    all_ranked = []
    for entry in base:
        sym = entry['symbol']
        direction = 1 if entry['move'] > 0 else -1 if entry['move'] < 0 else 0
        sector = sector_by_symbol.get(sym, 'OTHER')
        benchmark = sector_returns.get(sector)
        # Early ranking can proceed with incomplete relative-volume or NIFTY
        # baselines; unavailable metrics are explicitly marked as unavailable.
        if direction == 0 or (full and (entry['rvol'] is None or benchmark is None)):
            response['noTradeCount'] += 1
            continue
        available_rvol = entry['rvol'] if entry['rvol'] is not None else 0.0
        metrics = _direction_quality(entry['session'], entry['history'], direction, available_rvol)
        relative_nifty = direction * (entry['move'] - nifty) if nifty is not None else None
        relative_sector = direction * (entry['move'] - benchmark) if benchmark is not None else None
        if relative_nifty is not None and relative_sector is not None:
            strength = _clip(50 + 25 * min(1.5, relative_nifty) / 0.7 +
                             25 * min(1.5, relative_sector) / 0.7)
        else:
            strength = 50.0  # Neutral *score contribution*, never a fabricated benchmark reading.
        quality = _clip(0.25 * metrics['efficiency'] + 0.25 * metrics['persistenceQuality'] +
                        0.20 * metrics['alignmentScore'] + 0.15 * metrics['volumeScore'] +
                        0.15 * strength)
        if full:
            # Preserve the original post-10:00 strict qualification rules.
            reasons = []
            if metrics['turnover'] < MIN_TURNOVER_RUPEES: reasons.append('Low turnover')
            if entry['rvol'] < 1.5: reasons.append('RVOL < 1.5x')
            if metrics['efficiency'] < 60: reasons.append('Choppy path')
            if metrics['persistence'] < 60: reasons.append('Weak candle persistence')
            if not metrics['aligned']: reasons.append('VWAP/EMA disagreement')
            if not metrics['breakout']: reasons.append('No opening-range breakout')
            if relative_nifty <= 0 or relative_sector <= 0: reasons.append('Weak vs benchmark')
            if metrics['maxReversalPct'] > 1.3: reasons.append('Deep reversal')
            if quality < 70: reasons.append('Low direction quality')
            if reasons:
                response['noTradeCount'] += 1
                continue
        else:
            # Don't claim a completed opening-range breakout, EMA agreement,
            # or a stable multi-candle path based on one or two candles.
            # Exclude clearly choppy candidates as more bars complete.
            if count >= 3 and (metrics['efficiency'] < 30 or metrics['persistence'] < 40):
                response['noTradeCount'] += 1
                continue
        all_ranked.append({'symbol': sym, 'sector': sector,
                           'side': 'bullish' if direction > 0 else 'bearish',
                           'score': quality, 'rvol': entry['rvol'],
                           'relativeNifty': round(relative_nifty, 2) if relative_nifty is not None else None,
                           'relativeSector': round(relative_sector, 2) if relative_sector is not None else None,
                           'benchmarkSessions': entry['baselineSessions'],
                           'signalStage': 'qualified' if full else 'developing',
                           'candlesUsed': count, **metrics})
    response['eligibleCount'] = len(all_ranked)
    for side in ('bullish', 'bearish'):
        response[side] = sorted((r for r in all_ranked if r['side'] == side),
                                key=lambda r: (-r['score'], -r['efficiency'], -(r['rvol'] or 0), r['symbol']))[:5]
    response['noTradeCount'] += max(0, len(histories) - len(base))
    return response
