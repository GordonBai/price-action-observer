from datetime import datetime
import unittest

from pa_lens.robinhood import RobinhoodError, RobinhoodProvider

START = "2026-11-17T15:00:00Z"
END = "2026-11-17T15:20:00Z"
NOW = "2026-11-17T15:12:00+00:00"
TOOL = "get_equity_technical_indicators"


class IndicatorTests(unittest.TestCase):
    def provider(self, points, params=None):
        self.calls = []
        def transport(tool, args):
            self.calls.append((tool, args))
            return {"structuredContent": {"data": {"results": [
                {"symbol": name, "interval": args["interval"], "bounds": args["bounds"],
                 "indicators": [{"type": args["type"], "params": params or {}, "series": points}]}
                for name in args["symbols"]]}}}
        return RobinhoodProvider(transport, clock=lambda: datetime.fromisoformat(NOW),
                                 descriptors={TOOL: {"inputSchema": {}}})

    def test_exact_signed_and_null_macd_output_and_finality(self):
        provider = self.provider([
            {"begins_at": "2026-11-17T15:00:00Z", "macd": "-0.1234567890123456789",
             "signal": None, "histogram": -2},
            {"begins_at": "2026-11-17T15:05:00Z", "macd": 0, "signal": 0.01, "histogram": -0.01},
            {"begins_at": "2026-11-17T15:10:00Z", "macd": 7, "signal": 8, "histogram": 9},
        ], {"fast_period": 4, "slow_period": 5, "signal_period": 3})
        r = provider.indicators(["SOXL"], START, END, "macd", "5minute",
                                parameters={"fast_period": 4, "slow_period": 5, "signal_period": 3})
        self.assertEqual(self.calls[0][0], TOOL)
        self.assertEqual(self.calls[0][1]["fast_period"], 4)
        self.assertEqual(len(r.raw_records[0]["result"]["indicators"][0]["series"]), 3)
        points = r.series[0]["points"]
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["values"], {"macd": "-0.1234567890123456789",
                                               "signal": None, "histogram": "-2"})
        self.assertEqual(r.series[0]["latest"]["time"], "2026-11-17T15:10:00+00:00")
        self.assertEqual(r.quality["incomplete"], 1)
        self.assertEqual(r.quality["warmup"], "unknown")
        self.assertEqual(r.quality["source_quality"], "unknown")
        self.assertEqual(len(r.batches[0]["schema_sha256"]), 64)

    def test_schema_types_and_parameters(self):
        provider = self.provider([])
        parameter_cases = {"ema": {"period": 9}, "sma": {"period": None}, "rsi": {"period": 14},
                          "momentum": {}, "roc": {}, "cci": {}, "williams_r": {}, "atr": {},
                          "mfi": {}, "adx": {}, "donchian_channels": {"period": 20},
                          "bollinger_bands": {"num_std": 2.5}, "macd": {"signal_period": 5},
                          "keltner_channels": {"multiplier": 1.5}, "supertrend": {"multiplier": 3},
                          "vwap": {}, "obv": {}, "pivot_points": {"method": "classic"}}
        for typ, params in parameter_cases.items():
            with self.subTest(typ=typ):
                r = provider.indicators(["SOXL"], START, END, typ, "15second", parameters=params)
                self.assertEqual(r.series[0]["indicator_type"], typ)
                self.assertTrue(all((k not in self.calls[-1][1] if v is None else
                                     self.calls[-1][1][k] == v) for k, v in params.items()))
        for kwargs in ({"interval": "15minute"}, {"bounds": "trading"}, {"adjustment_type": "all"},
                       {"parameters": {"account_number": "xxx"}},
                       {"parameters": {"period": True}}, {"parameters": {"period": 0}},
                       {"output": "last:0"}, {"indicator_type": "unknown"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                provider.indicators(["SOXL"], START, END, **({"indicator_type": "ema",
                                                                 "interval": "minute"} | kwargs))
        with self.assertRaises(ValueError):
            provider._call("place_equity_order", {})
        self.assertEqual(len(self.calls), 18)

    def test_interday_raw_only_and_subminute_close(self):
        provider = self.provider([{"begins_at": START, "value": 100}])
        daily = provider.indicators(["SOXL"], START, END, "rsi", "week", adjustment_type="all")
        self.assertEqual(daily.series[0]["points"], [])
        self.assertEqual(daily.quality["raw_only"], 1)
        sub = provider.indicators(["SOXL"], START, END, "rsi", "30second")
        self.assertEqual(sub.series[0]["points"][0]["time"], "2026-11-17T15:00:30+00:00")

    def test_daily_next_midnight_and_trading_session_validation(self):
        provider = self.provider([{"begins_at": "2026-11-13T00:00:00Z", "value": 55},
                                  {"begins_at": "2026-11-14T00:00:00Z", "value": 70},
                                  {"begins_at": "2026-11-17T00:00:00Z", "value": 80}])
        r = provider.indicators(["SOXL"], "2026-11-13", "2026-11-17", "rsi", "day")
        self.assertEqual([p["time"] for p in r.series[0]["points"]], ["2026-11-14T00:00:00+00:00"])
        self.assertEqual(r.quality["invalid"], 1)
        self.assertEqual(r.quality["incomplete"], 1)
        self.assertEqual(self.calls[0][1]["start_time"], "2026-11-13T00:00:00Z")
        self.assertEqual(self.calls[0][1]["end_time"], "2026-11-18T00:00:00Z")

    def test_extended_daily_is_raw_only(self):
        provider = self.provider([{"begins_at": "2026-11-13T00:00:00Z", "value": 55}])
        r = provider.indicators(["SOXL"], "2026-11-13", "2026-11-17", "rsi", "day", bounds="extended")
        self.assertFalse(r.quality["normalization_supported"])
        self.assertEqual(r.quality["raw_only"], 1)
        self.assertIsNone(r.series[0]["latest"])

    def test_multifield_annotations_keep_null_not_zero(self):
        cases = {
            "donchian_channels": ["lower", "middle", "upper"],
            "bollinger_bands": ["lower", "middle", "upper"],
            "keltner_channels": ["lower", "middle", "upper"],
            "supertrend": ["value", "direction"],
            "pivot_points": ["pivot", "r1", "r2", "r3", "s1", "s2", "s3"],
        }
        for name, fields in cases.items():
            provider = self.provider([{"begins_at": START, **dict.fromkeys(fields, None),
                                       fields[-1]: -1}])
            r = provider.indicators(["SOXL"], START, END, name, "minute")
            self.assertEqual(r.series[0]["latest"]["values"], {**dict.fromkeys(fields, None),
                                                               fields[-1]: "-1"})
            self.assertEqual(r.quality["undefined_values"], len(fields)-1)

    def test_symbols_chunk_but_windows_remain_intact_and_change_identity(self):
        provider = self.provider([])
        args = ([f"A{i}" for i in range(11)], START, END, "ema", "minute")
        first = provider.indicators(*args, output="last:3")
        self.assertEqual([len(a["symbols"]) for _, a in self.calls], [10, 1])
        self.assertTrue(all(a["start_time"] == START and a["end_time"] == END
                            and a["output"] == "last:3" for _, a in self.calls))
        second = provider.indicators(["A0"], START, "2026-11-17T15:19:00Z", "ema", "minute")
        self.assertNotEqual(first.series[0]["series_id"], second.series[0]["series_id"])

    def test_forged_response_cannot_change_type(self):
        provider = RobinhoodProvider(lambda *_: {"data": {"results": [
             {"symbol": "SOXL", "interval": "minute", "bounds": "regular",
              "indicators": [{"type": "rsi", "params": {}, "series": []}]}]}},
             clock=lambda: datetime.fromisoformat(NOW))
        with self.assertRaises(RobinhoodError):
            provider.indicators(["SOXL"], START, END, "ema", "minute")

    def test_null_result_and_not_found_are_visible(self):
        provider = RobinhoodProvider(lambda *_: {"data": {"results": None, "not_found": ["SOXL"]}},
                                    clock=lambda: datetime.fromisoformat(NOW))
        r = provider.indicators(["SOXL"], START, END, "ema", "minute")
        self.assertFalse(r.series)
        self.assertEqual(r.quality["not_found"], ["SOXL"])
        self.assertEqual(r.quality["no_usable_symbols"], ["SOXL"])
