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
