from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from scanner_features import FiveMinuteBuilder, market_bucket, cumulative_slot_ratio, merge_finished, one_way_metrics, replay_session, breakout_signals

IST = ZoneInfo('Asia/Kolkata')
def stamp(h,m,day=8):
    return datetime(2026,10,day,h,m,tzinfo=IST)


def test_bucket_boundary_and_off_hours():
    assert market_bucket(stamp(9,19)) == stamp(9,15)
    assert market_bucket(stamp(9,20)) == stamp(9,20)
    assert market_bucket(stamp(15,30)) is None
    assert market_bucket(stamp(8,55)) is None


def test_cumulative_volume_and_completed_bars():
    c = FiveMinuteBuilder()
    assert c.ingest(stamp(9,15),100,120) is None
    assert c.ingest(stamp(9,17),102,220) is None
    complete = c.ingest(stamp(9,20),103,300)
    assert complete['open'] == 100
    assert complete['close'] == 102
    assert complete['volume'] == 220
    assert c.partial()['volume'] == 80
    assert c.ingest(stamp(9,19),150,1000) is None # out-of-order ignored
    assert c.partial()['high'] == 103


def test_merge_dedup_uses_latest_source():
    frame = pd.DataFrame([{'date':stamp(9,15),'open':100,'high':102,'low':99,'close':101,'volume':200}])
    rows = [{'date':stamp(9,15),'open':100,'high':103,'low':99,'close':103,'volume':270}]
    result = merge_finished(frame,rows)
    assert len(result)==1 and result.iloc[0]['close']==103


def test_time_slot_baseline_does_not_include_current_day():
    rows = []
    # five past sessions with same 09:15 and 09:20 slots.
    for day in [1,2,5,6,7]:
        rows += [{'date':stamp(9,15,day),'volume':100}, {'date':stamp(9,20,day),'volume':200}]
    frame=pd.DataFrame(rows)
    assert cumulative_slot_ratio(frame,600,stamp(9,20)) == 2.0
    assert cumulative_slot_ratio(frame,600,stamp(9,20,7)) is None  # too few prior sessions


def test_one_way_and_no_lookahead_replay():
    frame=pd.DataFrame([{'date':stamp(9,15)+timedelta(minutes=5*i),'open':100+i,'high':102+i,
        'low':99+i,'close':101+i,'volume':100+i*10} for i in range(10)])
    assert one_way_metrics(frame,1)['oneWay'] is True
    replay = replay_session(frame,date(2026,10,8))
    assert len(replay)==7
    assert replay[-1]['forward5m'] is None
    a = replay[0]['replayScore']
    changed=frame.copy()
    changed.loc[8,'close']=90000
    assert replay_session(changed,date(2026,10,8))[0]['replayScore']==a


def test_breakout_requires_cross_and_volume():
    frame=pd.DataFrame([{'open':100,'high':101,'low':99,'close':100},
       {'open':100,'high':102,'low':99,'close':101},
       {'open':101,'high':103,'low':100,'close':102},
       {'open':102,'high':103,'low':101,'close':102}])
    assert '15m ORB ↑' in breakout_signals(frame, None, 104, 2)
    assert breakout_signals(frame, None, 104, 1.0)==[]
