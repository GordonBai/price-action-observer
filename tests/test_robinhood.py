from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pa_lens.robinhood import RobinhoodError, RobinhoodProvider, open_robinhood


def bar(time, *, interpolated=False, high="11"):
    return {"begins_at": time, "open_price": "10", "high_price": high,
            "low_price": "9", "close_price": "10.5", "volume": 100,
            "session": "reg", "interpolated": interpolated}


class Stub:
    def __init__(self, rows=(), fail=None):
        self.rows = rows
        self.calls = []
        self.fail = fail

    def __call__(self, tool, args):
        self.calls.append((tool, args.copy()))
        if self.fail:
            raise RuntimeError(self.fail)
        if tool == "get_equity_quotes":
            rows = [{"quote": {"symbol": symbol, "last_trade_price": "10"}}
                    for symbol in args["symbols"]]
        else:
            rows = [{"symbol": symbol, "bounds": args["bounds"],
                     "interval": args["interval"], "bars": list(self.rows)}
                    for symbol in args["symbols"]]
        return {"structuredContent": {"data": {"results": rows}}}


class RobinhoodTests(unittest.TestCase):
    def provider(self, stub):
        return RobinhoodProvider(stub, descriptors={"get_equity_historicals": {"inputSchema": {}},
                                              "get_equity_quotes": {"inputSchema": {}}},
                                 clock=lambda: datetime(2026, 11, 17, 15, 3, tzinfo=timezone.utc))

    def fetch(self, stub, **kwargs):
        return self.provider(stub).fetch(["SOXL"], "2026-11-17T15:00:00Z",
                                         "2026-11-17T15:06:00Z", interval="minute", **kwargs)

    def test_final_interpolation_and_provenance(self):
        stub = Stub([bar("2026-11-17T15:00:00Z"), bar("2026-11-17T15:01:00Z", interpolated=True),
                     bar("2026-11-17T15:02:00Z", high="8"), bar("2026-11-17T15:03:00Z")])
        result = self.fetch(stub)
        self.assertEqual(len(result.bars), 1)
        self.assertEqual(result.bars[0].time, "2026-11-17T15:01:00+00:00")
        self.assertEqual(result.bars[0].source, result.source)
        self.assertEqual(result.source, "robinhood:minute:regular:split")
        self.assertEqual(result.quality["interpolated"], 1)
        self.assertEqual(result.quality["invalid"], 1)
        self.assertEqual(result.quality["incomplete"], 1)
        self.assertEqual(result.quality["interpolated_opens"], {"SOXL": ["2026-11-17T15:01:00+00:00"]})
        self.assertEqual(len(result.raw_records), 4)
        self.assertEqual(len(result.batches[0]["schema_sha256"]), 64)

    def test_caps_and_only_known_requests(self):
        stub = Stub()
        provider = self.provider(stub)
        result = provider.fetch([f"A{i}" for i in range(11)], "2026-11-01T00:00:00Z",
                                "2026-11-09T00:00:00Z", interval="minute", bounds="24_7")
        self.assertEqual(len(result.batches), 6)
        for tool, args in stub.calls:
            self.assertEqual(tool, "get_equity_historicals")
            self.assertLessEqual(len(args["symbols"]), 10)
            dt = datetime.fromisoformat(args["end_time"]) - datetime.fromisoformat(args["start_time"])
            self.assertLess(dt.total_seconds(), 5000 * 60)
        with self.assertRaises(ValueError):
            provider.fetch(["SOXL"], "2026-11-01T00:00:00Z", "2026-11-09T00:00:00Z",
                           interval="banana")
        with self.assertRaises(ValueError):
            provider.fetch(["SOXL"], "2026-11-01T00:00:00Z", "2026-11-09T00:00:00Z",
                           interval="day", adjustment_type="all")
        with self.assertRaises(ValueError):
            provider._call("place_equity_order", {})
        with self.assertRaises(ValueError):
            provider._call("get_equity_quotes", {"symbols": ["SOXL"], "account_number": "123"})
        self.assertEqual(len(stub.calls), 6)
        quote = provider.quotes(["SOXL"])
        self.assertEqual(stub.calls[-1], ("get_equity_quotes", {"symbols": ["SOXL"]}))
        self.assertEqual(quote.raw_records[0]["quote"]["symbol"], "SOXL")

    def test_exact_duplicates_and_conflict(self):
        x = bar("2026-11-17T15:00:00Z")
        result = self.fetch(Stub([x, x.copy()]))
        self.assertEqual(len(result.bars), 1)
        self.assertEqual(result.quality["duplicates"], 1)
        with self.assertRaisesRegex(RobinhoodError, "CONFLICT"):
            self.fetch(Stub([x, dict(x, volume=200)]))

    def test_inclusive_chunk_seam_deduped_and_safe_at_exclusive_end(self):
        x = bar("2026-11-04T11:19:00Z")  # exact 4,999-minute boundary
        y = bar("2026-11-04T11:20:00Z")
        z = bar("2026-11-04T11:21:00Z")
        provider = self.provider(Stub())
        def fetch(tool, args):
            rows = [r for r in (x, y, z) if datetime.fromisoformat(args["start_time"]) <=
                     datetime.fromisoformat(r["begins_at"].replace("Z", "+00:00")) <=
                     datetime.fromisoformat(args["end_time"])]
            return Stub(rows)(tool, args)
        provider = RobinhoodProvider(fetch, clock=provider._clock)
        result = provider.fetch(["SOXL"], "2026-11-01T00:00:00Z", "2026-11-04T11:21:00Z",
                                interval="minute")
        self.assertEqual([b.time for b in result.bars],
                         ["2026-11-04T11:20:00+00:00", "2026-11-04T11:21:00+00:00"])
        self.assertEqual(result.quality["duplicates"], 1)
        self.assertEqual(result.quality["out_of_range"], 1)

    def test_unknown_interpolation_never_reaches_engine(self):
        row = bar("2026-11-17T15:00:00Z")
        del row["interpolated"]
        result = self.fetch(Stub([row]))
        self.assertFalse(result.bars)
        self.assertEqual(result.quality["interpolation_unknown"], 1)
        self.assertEqual(result.quality["not_interpolated"], 0)
        self.assertEqual(result.quality["no_usable_symbols"], ["SOXL"])
        self.assertEqual(len(result.raw_records), 1)

    def test_exploratory_opt_in_keeps_unknown_provenance_and_rejects_true(self):
        missing = bar("2026-11-17T15:00:00Z")
        del missing["interpolated"]
        filled = bar("2026-11-17T15:01:00Z", interpolated=True)
        malformed = dict(bar("2026-11-17T15:02:00Z"), interpolated=None)
        strict = self.fetch(Stub([missing, filled, malformed]))
        opt_in = self.fetch(Stub([missing, filled, malformed]), accept_unknown=True)
        self.assertFalse(strict.bars)
        self.assertEqual(len(opt_in.bars), 1)
        self.assertEqual(opt_in.source, strict.source + ":accept_unknown")
        self.assertEqual(opt_in.bars[0].source, opt_in.source)
        self.assertEqual(opt_in.quality["unknown_emitted"], 1)
        self.assertEqual(opt_in.quality["status"], "DATA_QUALITY_UNKNOWN")
        self.assertEqual(opt_in.bar_provenance[0]["interpolation"], "unknown")
        self.assertEqual(opt_in.bar_provenance[0]["quality"], "DATA_QUALITY_UNKNOWN")
        self.assertEqual(opt_in.bar_provenance[0]["time"], opt_in.bars[0].time)
        self.assertEqual(opt_in.quality["interpolated"], 1)
        self.assertEqual(opt_in.quality["interpolation_unknown"], 2)

    def test_regular_session_and_minute_alignment(self):
        result = self.fetch(Stub([dict(bar("2026-11-17T15:00:00Z"), session="pre"),
                                  bar("2026-11-17T15:01:01Z")]))
        self.assertFalse(result.bars)
        self.assertEqual(result.quality["invalid"], 2)

    def test_receipt_time_cannot_promote_bar(self):
        times = iter(datetime.fromisoformat("2026-11-17T15:" + t + "+00:00")
                     for t in ("01:00", "01:04", "02:01"))
        provider = RobinhoodProvider(Stub([bar("2026-11-17T15:00:00Z"), bar("2026-11-17T15:01:00Z")]),
                                     clock=lambda: next(times))
        result = provider.fetch(["SOXL"], "2026-11-17T15:00:00Z", "2026-11-17T15:02:00Z")
        self.assertEqual(len(result.bars), 1)
        self.assertEqual(result.quality["incomplete"], 1)
        self.assertEqual(result.batches[0]["received_at"], "2026-11-17T15:02:01+00:00")

    def test_descriptor_unavailable_blocks_before_network(self):
        stub = Stub()
        with self.assertRaisesRegex(RobinhoodError, "TOOL_UNAVAILABLE"):
            RobinhoodProvider(stub, descriptors={"get_equity_historicals": {}}).quotes(["SOXL"])
        self.assertEqual(stub.calls, [])

    def test_daily_raw_only(self):
        stub = Stub([bar("2026-11-16T05:00:00Z")])
        result = self.provider(stub).fetch(["SOXL"], "2026-11-16T00:00:00Z",
                                           "2026-11-17T00:00:00Z", interval="day")
        self.assertFalse(result.bars)
        self.assertEqual(len(result.raw_records), 1)
        self.assertEqual(result.quality["daily_raw_only"], 1)

    def test_transport_failure_is_visible_without_raw_text(self):
        with self.assertRaises(RobinhoodError) as caught:
            self.fetch(Stub(fail="INTERACTIVE_AUTH_OR_APPROVAL_REQUIRED secret credentials"))
        self.assertEqual(str(caught.exception), "ROBINHOOD_AUTH_REQUIRED")
        self.assertTrue(caught.exception.__suppress_context__)

    def test_external_adapter_uses_only_read_entrypoint_and_closes(self):
        class InstalledAppServer:
            def __init__(self, **kwargs):
                self.tool_descriptors = {"get_equity_quotes": {},
                                         "place_equity_order": {}}

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                calls.append("close")

            def __call__(self, *args):
                raise AssertionError("legacy dispatcher must not run")

            def _read_call(self, tool, args):
                calls.append(tool)
                return Stub()(tool, args)

        calls = []
        fake_module = SimpleNamespace(CodexMarketTransport=InstalledAppServer)
        with patch("pa_lens.robinhood.importlib.import_module", return_value=fake_module) as load:
            with open_robinhood() as provider:
                self.assertEqual(provider.quotes(["SOXL"]).quality["received"], 1)
                with self.assertRaisesRegex(RobinhoodError, "TOOL_UNAVAILABLE"):
                    provider.fetch(["SOXL"], "2026-11-17T15:00:00Z", "2026-11-17T15:02:00Z")
            load.assert_called_once_with("trading_execution.transport")
        self.assertEqual(calls, ["get_equity_quotes", "close"])

    def test_unknown_schema_fails_closed(self):
        for payload in ({}, {"isError": True, "content": ["sensitive"]},
                        {"data": {"results": [{"symbol": "UNEXPECTED", "bars": []}]}}):
            provider = RobinhoodProvider(lambda *_: payload,
                clock=lambda: datetime(2026, 11, 17, 15, 3, tzinfo=timezone.utc))
            with self.assertRaises(RobinhoodError):
                provider.fetch(["SOXL"], "2026-11-17T15:00:00Z", "2026-11-17T15:02:00Z")
