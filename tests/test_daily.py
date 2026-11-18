import unittest
from datetime import date, timedelta
from pa_lens.core import Bar, Engine
from pa_lens.analytics import LocalIndicators
from pa_lens.audit import audit_bars, future_path
from pa_lens.replay import evaluate
from dataclasses import replace

def day(label, price=100, source="test"):
    end = date.fromisoformat(label) + timedelta(days=1)
    return Bar("TEST", "D", str(end)+"T00:00:00Z", price,price+2,price-1,price,1,source)

class DailyTests(unittest.TestCase):
    def test_calendar(self):
        bars=[day(t, 100+i) for i,t in enumerate(["2026-10-30","2026-11-02","2026-11-04"])]
        e=Engine()
        for b in bars[:2]: e.update(b)
        self.assertEqual(len(e.bars),2)
        self.assertEqual(e.update(bars[2])[0]["family"],"data_gap")
        self.assertEqual(e.snapshot()["local_indicators"]["bars"],1)
        self.assertEqual(future_path(bars,0,3)["bars_observed"],1)
        with self.assertRaises(ValueError): day("2026-11-26")
        bars=[day(t,100+i) for i,t in enumerate(["2026-11-25","2026-11-27","2026-11-30"])]
        a=audit_bars(bars)["summary"]
        self.assertTrue(a["prefix_consistency"]["passed"])
        self.assertIsNone(a["display_projection"]["observed_hours"])
        self.assertEqual(a["unexpected_gaps"],0)
        with self.assertRaisesRegex(ValueError,"intraday"): evaluate(bars,[])
    def test_prefix_detects_inside_bar_without_next_session(self):
        bars=[day("2026-11-25"),replace(day("2026-11-27"),low=99.5,high=101),
              replace(day("2026-11-30"),low=99.6,high=100.5)]
        a=audit_bars(bars)
        self.assertEqual([x["event"]["family"] for x in a["events"]].count("inside_bar"),2)
        self.assertTrue(a["summary"]["prefix_consistency"]["passed"])
        self.assertTrue(all(x["event"]["family"] not in ("opening_reversal","higher_timeframe_bar") for x in a["events"]))
    def test_indicators(self):
        a=LocalIndicators()
        for i in range(15):
            a.update(day("2026-11-02",100+i))
            if i<14: self.assertIsNone(a.snapshot()["rsi14"]["value"])
        self.assertEqual(a.snapshot()["rsi14"]["value"],100)
        a.update(day("2026-11-02",113))
        self.assertAlmostEqual(a.snapshot()["rsi14"]["value"],100*13/14)
        self.assertAlmostEqual(a.snapshot()["ema20"]["value"],100+15-9.5*(1-(19/21)**15)-4/21)
    def test_quality(self):
        e=Engine();e.update(day("2026-11-02",source="robinhood:day:regular:split:accept_unknown"))
        events=e.update(day("2026-11-04",source="robinhood:day:regular:split:accept_unknown"))
        for obj in [e.snapshot(), *events]:self.assertEqual(obj["data_quality"],"DATA_QUALITY_UNKNOWN")
    def test_xnys_session_close_early_close_and_intraday_cutoff(self):
        from datetime import datetime, timezone
        from pa_lens.timeframes import consecutive_daily, daily_close, daily_session, is_daily_fresh, next_daily_close
        from pa_lens.robinhood import RobinhoodProvider
        # Regular session 2026-11-18 closes 16:00 EST = 21:00 UTC
        reg_close = daily_close("2026-11-18")
        self.assertEqual(reg_close.isoformat(), "2026-11-18T21:00:00+00:00")
        self.assertEqual(daily_session(reg_close), "2026-11-18")
        # Black Friday 2026-11-27 early close 13:00 EST = 18:00 UTC
        early_close = daily_close("2026-11-27")
        self.assertEqual(early_close.isoformat(), "2026-11-27T18:00:00+00:00")
        self.assertEqual(daily_session(early_close), "2026-11-27")
        # Mid-session 14:30 EST (19:30 UTC) excludes today's unfinished daily bar; 16:05 EST emits it
        rows = [{"begins_at": "2026-11-17T00:00:00Z", "open_price": "10", "high_price": "11", "low_price": "9", "close_price": "10.5", "volume": 100, "session": "reg", "interpolated": False},
                {"begins_at": "2026-11-18T00:00:00Z", "open_price": "10.5", "high_price": "12", "low_price": "10", "close_price": "11.5", "volume": 120, "session": "reg", "interpolated": False}]
        payload = lambda _t, a: {"data": {"results": [{"symbol": "SOXL", "interval": "day", "bounds": "regular", "bars": rows}]}}
        mid = RobinhoodProvider(payload, clock=lambda: datetime(2026, 11, 18, 19, 30, tzinfo=timezone.utc)).fetch(
            ["SOXL"], "2026-11-17T00:00:00Z", "2026-11-18T19:30:00Z", interval="day")
        self.assertEqual([b.time for b in mid.bars], ["2026-11-17T21:00:00+00:00"])
        self.assertEqual(mid.quality["incomplete"], 1)
        after = RobinhoodProvider(payload, clock=lambda: datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)).fetch(
            ["SOXL"], "2026-11-17T00:00:00Z", "2026-11-18T21:05:00Z", interval="day")
        self.assertEqual([b.time for b in after.bars], ["2026-11-17T21:00:00+00:00", "2026-11-18T21:00:00+00:00"])
        # Black Friday 17:55 UTC incomplete vs 18:05 UTC emitted
        bf_rows = [{"begins_at": "2026-11-27T00:00:00Z", "open_price": "10", "high_price": "11", "low_price": "9", "close_price": "10.5", "volume": 50, "session": "reg", "interpolated": False}]
        bf_payload = lambda _t, a: {"data": {"results": [{"symbol": "SOXL", "interval": "day", "bounds": "regular", "bars": bf_rows}]}}
        self.assertEqual(len(RobinhoodProvider(bf_payload, clock=lambda: datetime(2026, 11, 27, 17, 55, tzinfo=timezone.utc)).fetch(
            ["SOXL"], "2026-11-27T00:00:00Z", "2026-11-27T17:55:00Z", interval="day").bars), 0)
        self.assertEqual([b.time for b in RobinhoodProvider(bf_payload, clock=lambda: datetime(2026, 11, 27, 18, 5, tzinfo=timezone.utc)).fetch(
            ["SOXL"], "2026-11-27T00:00:00Z", "2026-11-27T18:05:00Z", interval="day").bars], ["2026-11-27T18:00:00+00:00"])
        # Weekend & Monday daytime freshness: Friday 2026-11-20 21:00 UTC stays fresh on Sunday night and Monday 15:00 EST, stale Monday 18:30 EST
        fri = daily_close("2026-11-20")
        self.assertTrue(is_daily_fresh(fri, datetime(2026, 11, 23, 1, 0, tzinfo=timezone.utc)))   # Sunday 20:00 EST
        self.assertTrue(is_daily_fresh(fri, datetime(2026, 11, 23, 20, 0, tzinfo=timezone.utc)))  # Monday 15:00 EST
        self.assertTrue(is_daily_fresh(fri, datetime(2026, 11, 23, 21, 30, tzinfo=timezone.utc))) # Monday 16:30 EST (within 2h grace)
        self.assertFalse(is_daily_fresh(fri, datetime(2026, 11, 23, 23, 30, tzinfo=timezone.utc)))# Monday 18:30 EST (past 2h grace)
        self.assertFalse(is_daily_fresh(fri, datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc))) # Future close vs now
        self.assertTrue(consecutive_daily(daily_close("2026-11-25"), early_close))
        self.assertEqual(next_daily_close(datetime(2026, 11, 27, 17, 59, 0, tzinfo=timezone.utc), 10), 70)

