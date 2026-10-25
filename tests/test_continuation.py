"""Run: python3 -m unittest discover -s tests -v (no Kite credentials needed)."""
import sys
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from continuation_radar import scan_continuation, _normalise, cutoff_for

IST = ZoneInfo('Asia/Kolkata')
TEST_DAY = date(2026, 10, 26)  # Monday


def candles_for(direction=1, session_vol=70_000, choppy=False, step=.65):
    days = []
    d = TEST_DAY-timedelta(days=1)
    while len(days) < 12:
        if d.weekday() < 5: days.append(d)
        d -= timedelta(days=1)
    days = sorted(days) + [TEST_DAY]
    rows = []
    for d in days:
        is_today = d == TEST_DAY
        anchor = datetime.combine(d,time(9,15), tzinfo=IST)
        for i in range(75 if not is_today else 11):
            if is_today:
                if choppy:
                    price = 100 + (0.5 if i%2==0 else -0.5)
                    price2 = 100 + (0.5 if i%2 else -0.5)
                else:
                    price = 100 + direction * i * step
                    price2 = 100 + direction * (i+1) * step
            else:
                price = 100 + .003*i
                price2 = price + .003
            hi = max(price,price2)+.05
            lo = min(price,price2)-.05
            rows.append({'date': anchor + timedelta(minutes=5*i), 'open': price,
                         'high': hi, 'low': lo, 'close': price2,
                         'volume': session_vol if is_today else 16000})
    return rows


def screen_inputs():
    syms = [f'NX{i}' for i in range(12)]
    histories = {s: candles_for(direction=1, step=.2) for s in syms}
    histories['UP'] = candles_for(direction=1, session_vol=150_000)
    histories['DOWN'] = candles_for(direction=-1, session_vol=150_000)
    histories['CHOP'] = candles_for(direction=1, choppy=True, session_vol=160_000)
    sectors = {'NIFTY_50':syms, 'METAL': ['UP','DOWN','CHOP'], 'IT':syms}
    return histories, sectors


class ContinuationTests(unittest.TestCase):
    def test_cutoff_rounding(self):
        self.assertEqual(cutoff_for(datetime(2026,10,26,9,58,tzinfo=IST)).time(), time(9,55))
        self.assertEqual(cutoff_for(datetime(2026,10,26,10,0,tzinfo=IST)).time(), time(10,0))

    def test_completed_candles_only(self):
        raw = candles_for()
        cut = datetime(2026,10,26,10,0,tzinfo=IST)
        today = [x for x in _normalise(raw,cut) if x['date'].date() == cut.date()]
        self.assertEqual(len(today),9)
        self.assertEqual(today[-1]['date'].time(),time(9,55))

    def test_first_bar_collecting_before_920(self):
        histories, sectors = screen_inputs()
        result = scan_continuation(histories, sectors, datetime(2026,10,26,9,19,tzinfo=IST))
        self.assertEqual(result['status'], 'collecting_first_candle')
        self.assertFalse(result['bullish'])

    def test_developing_at_920(self):
        histories, sectors = screen_inputs()
        result = scan_continuation(histories, sectors, datetime(2026,10,26,9,20,tzinfo=IST))
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['phase'], 'developing')
        self.assertEqual(result['completedCandles'], 1)
        self.assertFalse(result['openingRangeReady'])
        self.assertTrue(result['bullish'])
        self.assertTrue(result['bearish'])
        self.assertTrue(all(not r['breakout'] for r in result['bullish'] + result['bearish']))
        self.assertTrue(all(r['signalStage'] == 'developing' for r in result['bullish'] + result['bearish']))

    def test_before_10_provisional_rankings(self):
        histories, sectors = screen_inputs()
        result = scan_continuation(histories, sectors, datetime(2026,10,26,9,59,tzinfo=IST))
        self.assertEqual(result['phase'], 'developing')
        self.assertEqual(result['completedCandles'], 8)
        self.assertTrue(result['openingRangeReady'])
        self.assertIn('UP', [r['symbol'] for r in result['bullish']])

    def test_progresses_only_with_new_completed_bar(self):
        histories, sectors = screen_inputs()
        at_925 = scan_continuation(histories, sectors, datetime(2026,10,26,9,25,tzinfo=IST))
        at_928 = scan_continuation(histories, sectors, datetime(2026,10,26,9,28,tzinfo=IST))
        at_930 = scan_continuation(histories, sectors, datetime(2026,10,26,9,30,tzinfo=IST))
        self.assertEqual(at_925, at_928)
        self.assertEqual(at_925['completedCandles'], 2)
        self.assertEqual(at_930['completedCandles'], 3)
        self.assertNotEqual(at_925['asOf'], at_930['asOf'])

    def test_945_opening_range_established_but_breakout_not_implied(self):
        histories, sectors = screen_inputs()
        result = scan_continuation(histories, sectors, datetime(2026,10,26,9,45,tzinfo=IST))
        self.assertTrue(result['openingRangeReady'])
        self.assertEqual(result['completedCandles'], 6)
        self.assertTrue(all(not r['breakout'] for r in result['bullish'] + result['bearish']))

    def test_early_missing_benchmark_or_rvol_is_marked_not_invented(self):
        histories, sectors = screen_inputs()
        sectors['NIFTY_50'] = ['NX0', 'NX1']
        histories['UP'] = [x for x in histories['UP'] if x['date'].date() == TEST_DAY]
        histories = {symbol: rows for symbol, rows in histories.items() if symbol in {'NX0', 'NX1', 'UP', 'DOWN'}}
        result = scan_continuation(histories, sectors, datetime(2026,10,26,9,20,tzinfo=IST))
        self.assertEqual(result['phase'], 'developing')
        self.assertFalse(result['benchmarkReady'])
        self.assertIn('UP', [r['symbol'] for r in result['bullish']])
        up = next(r for r in result['bullish'] if r['symbol'] == 'UP')
        self.assertIsNone(up['rvol'])
        self.assertIsNone(up['relativeNifty'])

    def test_early_cutoff_no_lookahead(self):
        histories, sectors = screen_inputs()
        cut = datetime(2026,10,26,9,20,tzinfo=IST)
        before = scan_continuation(histories, sectors, cut)
        for rows in histories.values():
            for candle in rows:
                if candle['date'].date() == TEST_DAY and candle['date'].time() >= time(9,20):
                    candle['close'] = 1_000_000
                    candle['high'] = 1_000_000
                    candle['volume'] = 100_000_000
        self.assertEqual(before, scan_continuation(histories, sectors, cut))

    def test_full_screen_starts_at_1000(self):
        histories, sectors = screen_inputs()
        result = scan_continuation(histories, sectors, datetime(2026,10,26,10,0,tzinfo=IST))
        self.assertEqual(result['phase'], 'confirmed_screen')
        self.assertEqual(result['completedCandles'], 9)
        self.assertTrue(all(r['signalStage'] == 'qualified' for r in result['bullish'] + result['bearish']))

    def test_no_lookahead(self):
        histories, sectors = screen_inputs()
        cut = datetime(2026,10,26,10,0,tzinfo=IST)
        prior = scan_continuation(histories,sectors,cut)
        histories['UP'][-1]['close']=1_000_000
        histories['UP'][-1]['high']=1_000_000
        after = scan_continuation(histories,sectors,cut)
        self.assertEqual(prior,after)

    def test_benchmark_proxy_needs_coverage(self):
        histories, sectors = screen_inputs()
        sectors['NIFTY_50'] = sectors['NIFTY_50'][:4]
        result = scan_continuation(histories,sectors,datetime(2026,10,26,10,0,tzinfo=IST))
        self.assertEqual(result['status'],'waiting_for_benchmark')

    def test_rvol_no_future_baseline(self):
        histories, sectors = screen_inputs()
        cut=datetime(2026,10,26,10,0,tzinfo=IST)
        before=scan_continuation(histories,sectors,cut)
        # Add a high-volume day AFTER the snapshot to all history series.
        future = datetime(2026,10,27,9,15,tzinfo=IST)
        for rows in histories.values():
            rows.append({'date':future,'open':101,'high':102,'low':100,'close':101,'volume':100000000})
        self.assertEqual(before,scan_continuation(histories,sectors,cut))

    def test_missing_history_no_invented_rvol(self):
        histories, sectors = screen_inputs()
        histories['UP'] = [c for c in histories['UP'] if c['date'].date()==TEST_DAY]
        result=scan_continuation(histories,sectors,datetime(2026,10,26,10,0,tzinfo=IST))
        self.assertTrue(all(r['symbol']!='UP' for r in result['bullish']))

    def test_choppy_excluded(self):
        histories,sectors = screen_inputs()
        result=scan_continuation(histories,sectors,datetime(2026,10,26,10,0,tzinfo=IST))
        self.assertTrue(all(r['symbol']!='CHOP' for r in result['bullish']+result['bearish']))

    def test_rankings_and_limits(self):
        histories,sectors = screen_inputs()
        result=scan_continuation(histories,sectors,datetime(2026,10,26,10,0,tzinfo=IST))
        self.assertEqual(result['status'],'ok')
        self.assertLessEqual(len(result['bullish']),5)
        self.assertLessEqual(len(result['bearish']),5)
        self.assertIn('UP', [r['symbol'] for r in result['bullish']])
        self.assertIn('DOWN', [r['symbol'] for r in result['bearish']])
        for side in ['bullish','bearish']:
            scores=[r['score'] for r in result[side]]
            self.assertEqual(scores,sorted(scores,reverse=True))

    def test_missing_middle_candle_excluded(self):
        histories,sectors=screen_inputs()
        histories['UP'] = [r for r in histories['UP'] if not (r['date'].date()==TEST_DAY and r['date'].time()==time(9,35))]
        result=scan_continuation(histories,sectors,datetime(2026,10,26,10,0,tzinfo=IST))
        self.assertNotIn('UP',[r['symbol'] for r in result['bullish']])


if __name__ == '__main__': unittest.main()
