from datetime import datetime
import unittest

from pa_lens.terminal_monitor import TerminalMonitor

SRC = "robinhood:minute:regular:split"
T10 = "2026-11-18T15:10:00Z"
T11 = "2026-11-18T15:11:00Z"
T12 = "2026-11-18T15:12:00Z"


def dt(time):
    return datetime.fromisoformat(time.replace("Z", "+00:00"))


def event(id_, when, family="double_bottom"):
    return dict(id=id_, observed_at=when, family=family, status="confirmed",
                direction="bull", explanation="Structure closed above neckline.")


def stream(close, *, events=(), symbol="SOXL", freshness="RECENT", quarantined=0,
           quality=None, native=None, source=SRC):
    return {
        "symbol": symbol, "timeframe": "1", "source": source, "last_bar_close": close,
        "age_seconds": 5, "freshness": freshness, "readiness": "READY_FOR_RESEARCH",
        "bars": [{"time": close, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100}],
        "state": {"context": "trend_up"},
        "data_quality": {"status": "DATA_REVIEW_REQUIRED" if quarantined else quality,
                         "quarantined_count": quarantined},
        "display": {"groups": [{"events": list(events)}]},
        "native_interpretation": native or {"status": "UNAVAILABLE", "reason": "No matching snapshot"}
    }


class TerminalMonitorTests(unittest.TestCase):
    def render(self, monitor, streams, now, status="ELIGIBLE_OBSERVATIONS", *, fixed=False):
        return monitor.render({"streams": streams}, [(("SOXL",), {"status": status})],
                              now=dt(now), source=SRC, fixed_end=fixed)

    def test_first_snapshot_is_baseline_then_new_id_once(self):
        monitor = TerminalMonitor(["SOXL"])
        bootstrap = self.render(monitor, [stream(T10, events=[event("old-id", T10)])], T10)
        self.assertIn("BASELINE", bootstrap)
        self.assertIn("O=10 H=12 L=9 C=11 V=100", bootstrap)
        self.assertIn("2026-11-18 10:10:00 EST", bootstrap)
        self.assertNotIn("old-id", bootstrap)
        new = event("new-id", T11)
        second = self.render(monitor, [stream(T11, events=[event("old-id", T10), new, new])], T11)
        self.assertEqual(second.count("new-id"), 1)
        self.assertIn("double_bottom", second)
        self.assertIn("Structure closed above neckline", second)
        self.assertNotIn("old-id", second)
        again = self.render(monitor, [stream(T12, events=[dict(new, observed_at=T12)])], T12)
        self.assertNotIn("new-id", again)
        self.assertIn("No new key PA event", again)

    def test_stale_fixed_end_and_quarantine_not_promoted(self):
        monitor = TerminalMonitor(["SOXL"])
        self.render(monitor, [stream(T10)], T10)
        stale = self.render(monitor, [stream(T11, events=[event("stale-id", T11)],
                                             freshness="STALE")], "2026-11-18T15:20:00Z")
        self.assertIn("STALE", stale)
        self.assertNotIn("stale-id", stale)
        quarantined = self.render(monitor, [stream(T12, events=[event("q-id", T12)],
                                                   quarantined=2)], T12)
        self.assertIn("QUARANTINE", quarantined)
        self.assertIn("first-received", quarantined)
        self.assertNotIn("q-id", quarantined)
        T13 = "2026-11-18T15:13:00Z"
        fixed = self.render(monitor, [stream(T13, events=[event("fix-id", T13)])], T13, fixed=True)
        self.assertIn("FIXED END", fixed)
        self.assertNotIn("fix-id", fixed)

    def test_no_data_then_baseline_and_unknown_native_is_explicit(self):
        monitor = TerminalMonitor(["SOXL"])
        empty = self.render(monitor, [], T10, "NO_USABLE_BARS")
        self.assertIn("No accepted closed bar", empty)
        native = {"status": "PARTIAL_NATIVE_CONTEXT", "ema20": {"status": "AVAILABLE_SOURCE_UNKNOWN",
                   "value": "10.5", "relation": "above", "effective_at": T11},
                  "rsi14": {"status": "UNAVAILABLE", "reason": "native snapshot is stale"}}
        baseline = self.render(monitor, [stream(T11, quality="DATA_QUALITY_UNKNOWN", native=native)], T11,
                               "DATA_QUALITY_UNKNOWN")
        for label in ("BASELINE", "DATA_QUALITY_UNKNOWN", "EMA20", "10.5", "above", "native snapshot is stale",
                      "warmup/source quality unknown", "trend_up"):
            self.assertIn(label, baseline)

    def test_recent_bar_does_not_promote_older_catchup_event(self):
        monitor = TerminalMonitor(["SOXL"])
        self.render(monitor, [stream(T10)], T10)
        later = "2026-11-18T15:20:00Z"
        text = self.render(monitor, [stream(later, events=[event("historical", T11), event("current", later)])], later)
        self.assertNotIn("historical", text)
        self.assertIn("id=current", text)

    def test_multiple_symbols_keep_per_cycle_acquisition_status(self):
        monitor = TerminalMonitor(["SOXL", "SPY"])
        rows = [stream(T10), stream(T10, symbol="SPY")]
        text = monitor.render({"streams": rows},
            [(("SOXL", "SPY"), {"status": "PARTIAL_DATA", "quality": {"no_usable_symbols": ["SPY"]}})],
            now=dt(T10), source=SRC, native_enabled=False)
        self.assertIn("SOXL | acquisition=PARTIAL_DATA", text)
        self.assertIn("SPY | acquisition=NO_USABLE_BARS", text)
        self.assertIn("not confirmed by this poll", text)
        self.assertIn("NOT REQUESTED", text)

    def test_cli_text_and_machine_formats(self):
        from contextlib import redirect_stdout
        from datetime import timedelta, timezone
        from io import StringIO
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        from pa_lens.__main__ import main

        observed = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1)
        def acquire(_provider, journal, symbols, _start, _end, **_kwargs):
            journal.ingest_observation(dict(symbol=symbols[0], timeframe="1", source=SRC,
                time=observed.isoformat(), open=10, high=12, low=9, close=11, volume=100))
            return {"status": "ELIGIBLE_OBSERVATIONS"}

        with TemporaryDirectory() as tmp:
            for format_ in ("text", "jsonl", None):
                out = StringIO()
                argv = ["pa_lens", "poll-robinhood", "--no-native-context", "--once",
                        "--db", str(Path(tmp) / f"{format_}.db")]
                if format_:
                    argv += ["--output", format_]
                with patch("sys.argv", argv), patch("pa_lens.robinhood.open_robinhood"), \
                     patch("pa_lens.rh_runtime.acquire", side_effect=acquire), redirect_stdout(out):
                    main()
                if format_ == "text":
                    self.assertIn("Latest journaled 1m closed bar", out.getvalue())
                    self.assertIn("history loaded", out.getvalue())
                else:
                    records = [json.loads(line) for line in out.getvalue().splitlines()]
                    self.assertEqual(records[0]["status"], "ELIGIBLE_OBSERVATIONS")
                    self.assertIn("native_pa_context", records[1])

    def test_tui_layout_fits_80_and_120_columns_and_keeps_quality_visible(self):
        from pa_lens.terminal_monitor import format_tui, visible_width
        old = event("archive-id", T10)
        monitor = TerminalMonitor(["SOXL"])
        def view():
            return monitor.view({"streams": [stream(T10, events=[old], freshness="STALE",
                                                   quality="DATA_QUALITY_UNKNOWN")]},
                                [(("SOXL",), {"status": "DATA_QUALITY_UNKNOWN"})],
                                now=dt(T11), source=SRC)
        for width, height in ((80, 24), (120, 33), (52, 28)):
            frame = format_tui(view(), width=width, height=height)
            for heading in ("MARKET", "NATIVE INDICATORS", "PRICE ACTION", "DATA QUALITY"):
                self.assertIn(heading, frame)
            self.assertIn("STALE", frame)
            self.assertIn("DATA_QUALITY_UNKNOWN", frame)
            self.assertIn("HISTORY", frame)
            self.assertNotIn("NEW PA", frame)
            self.assertLessEqual(len(frame.splitlines()), height)
            self.assertTrue(all(visible_width(line) <= width for line in frame.splitlines()))

    def test_explicit_tui_without_terminal_falls_back_to_plain_text(self):
        from unittest.mock import patch
        from io import StringIO
        from pa_lens.terminal_monitor import terminal_output
        stream_ = StringIO()
        self.assertEqual(terminal_output("tui", stream_), "text")
        with patch.object(stream_, "isatty", return_value=True), patch.dict(
                "os.environ", {"TERM": "xterm-256color"}):
            self.assertEqual(terminal_output("tui", stream_), "tui")
        with patch.object(stream_, "isatty", return_value=True), patch.dict(
                "os.environ", {"TERM": "dumb"}):
            self.assertEqual(terminal_output("tui", stream_), "text")

    def test_tui_history_and_new_both_show_engine_judgment_under_separate_labels(self):
        from pa_lens.terminal_monitor import format_tui

        monitor = TerminalMonitor(["SOXL"])
        old = event("prior", T10)
        receipts = [(("SOXL",), {"status": "ELIGIBLE_OBSERVATIONS"})]
        baseline = monitor.view({"streams": [stream(T10, events=[old])]}, receipts,
                                now=dt(T10), source=SRC)
        history = format_tui(baseline, width=80, height=24)
        self.assertIn("HISTORY", history)
        self.assertIn("not new", history)
        self.assertIn("Structure closed above neckline.", history)
        self.assertIn("Structure closed above neckline.", baseline["text"])
        self.assertNotIn("NEW PA", history)

        new = dict(event("fresh", T11), explanation="Confirmed on the closing bar.")
        next_view = monitor.view({"streams": [stream(T11, events=[old, new])]}, receipts,
                                 now=dt(T11), source=SRC)
        live = format_tui(next_view, width=80, height=24)
        self.assertIn("NEW PA", live)
        self.assertIn("Confirmed on the closing bar.", live)
        self.assertNotIn("HISTORY", live)

    def test_tui_top_risk_never_hidden_by_other_symbols_or_small_viewport(self):
        from pa_lens.terminal_monitor import format_tui

        monitor = TerminalMonitor(["SOXL", "SPY", "QQQ", "IWM"])
        snapshot = {"streams": [stream(T10), stream(T10, symbol="SPY", quarantined=2),
            stream(T10, symbol="QQQ", freshness="STALE", quality="DATA_QUALITY_UNKNOWN")],
            "transport": [{"symbol": "IWM", "source": SRC, "status": "error"}]}
        receipts = [(("SOXL", "SPY", "QQQ"), {"status": "ELIGIBLE_OBSERVATIONS"})]
        view = monitor.view(snapshot, receipts, now=dt(T10), source=SRC)
        for width, height in ((80, 17), (80, 24), (42, 8)):
            frame = format_tui(view, width=width, height=height)
            header = "\n".join(frame.splitlines()[:6])
            for label in ("QUARANTINE 1", "UNKNOWN 1", "STALE 1", "ERROR 1"):
                self.assertIn(label, header)
            if height >= 17:
                self.assertIn("omitted", frame)
            else:
                self.assertIn("Enlarge", frame)

    def test_clock_frame_separates_wall_pull_receipt_and_ages_cached_bar(self):
        from pa_lens.terminal_monitor import clock_frame, format_tui
        monitor = TerminalMonitor(["SOXL"])
        native = {"status": "AVAILABLE_SOURCE_UNKNOWN",
                  "ema20": {"status": "AVAILABLE_SOURCE_UNKNOWN", "value": "123.456",
                            "effective_at": T10}}
        snapshot = {"streams": [stream(T10, native=native)], "acquisitions": [{
            "id": 7, "source": SRC, "received_at": "2026-11-18T15:10:06Z"}]}
        view = monitor.view(snapshot, [(("SOXL",), {"status": "ELIGIBLE_OBSERVATIONS",
            "acquisition_id": 7})], now=dt(T10), source=SRC)
        wall = dt("2026-11-18T15:12:01Z")
        live = clock_frame(view, wall, "PULLING", dt(T12))
        text = format_tui(live, width=120, height=28)
        for label in ("NY NOW 2026-11-18 10:12:01 EST", "Pull start 2026-11-18 10:12:00 EST",
                      "Bars received 2026-11-18 10:10:06 EST", "Snapshot 121s old", "STALE",
                      "2026-11-18 10:10:00 EST", "EMA20  STALE", SRC):
            self.assertIn(label, text)
        self.assertNotIn("READY_FOR_RESEARCH", text)
        self.assertNotIn("123.456", text)
        self.assertNotIn("STALE", format_tui(view, width=120, height=28))

    def test_clock_renderer_ticks_during_blocked_main_and_leaves_final_frame(self):
        from datetime import timedelta
        from io import StringIO
        from itertools import count
        from queue import Queue
        from types import SimpleNamespace
        from pa_lens.terminal_monitor import TuiClock

        class Output(StringIO):
            def write(self, value):
                result = super().write(value)
                if value.startswith("\x1b"):
                    updates.put(value)
                return result

        updates = Queue()
        calls = (dt(T10) + timedelta(seconds=second) for second in count())
        out = Output()
        clock = TuiClock(out, source=SRC, symbols=["SOXL"], clock=lambda: next(calls),
                         size=lambda: SimpleNamespace(columns=120, lines=28),
                         tick_seconds=0.01, color=False)
        clock.start()
        before = updates.get(timeout=2)
        following = updates.get(timeout=2)
        self.assertIn("CONNECTING", before)
        self.assertNotEqual(before, following)
        monitor = TerminalMonitor(["SOXL"])
        view = monitor.view({"streams": [stream(T10)]}, [], now=dt(T10), source=SRC)
        clock.publish(view)
        clock.status("PULLING", pull_started=dt(T11))
        in_flight = []
        for _ in range(8):
            candidate = updates.get(timeout=2)
            if "PULLING" in candidate and "2026-11-18 10:10:00 EST" in candidate:
                in_flight.append(candidate)
            if len(in_flight) == 2:
                break
        clock.close()
        self.assertEqual(len(in_flight), 2)
        self.assertNotEqual(*in_flight)
        self.assertFalse(clock.running)
        self.assertIn("SOXL", out.getvalue().split("\x1b[2J")[-1])
        self.assertIn("Snapshot", out.getvalue().split("\x1b[2J")[-1])

    def test_dates_roll_back_to_new_york_and_dst_fold_retains_zone_labels(self):
        from pa_lens.terminal_monitor import clock_frame, format_tui
        close = "2026-07-02T00:01:00Z"
        wall = dt("2026-07-02T00:01:10Z")
        native = {"status": "AVAILABLE_SOURCE_UNKNOWN", "ema20": {
            "status": "AVAILABLE_SOURCE_UNKNOWN", "value": "12.50", "effective_at": close}}
        snapshot = {"streams": [stream(close, events=[event("p", close)], native=native)],
                    "acquisitions": [{"id": 2, "source": SRC, "received_at": "2026-07-02T00:01:06Z"}]}
        monitor = TerminalMonitor(["SOXL"])
        view = monitor.view(snapshot, [(("SOXL",), {"acquisition_id": 2})], now=wall, source=SRC)
        rendered = format_tui(clock_frame(view, wall, "WAITING", dt(close)), width=120, height=31)
        for label in ("NY NOW 2026-07-01 20:01:10 EDT", "Pull start 2026-07-01 20:01:00 EDT",
                      "Bars received 2026-07-01 20:01:06 EDT", "Effective 2026-07-01 20:01:00 EDT",
                      "HISTORY"):
            self.assertIn(label, rendered)
        self.assertNotIn("2026-07-02", rendered)
        self.assertIn("effective 2026-07-01 20:01:00 EDT", view["text"])
        self.assertIn("HISTORY (not new) 2026-07-01 20:01:00 EDT", view["text"])
        for utc, tz in (("2026-11-01T05:30:00Z", "EDT"), ("2026-11-01T06:30:00Z", "EST")):
            moment = dt(utc)
            folded = clock_frame(view, moment, "PULLING", moment)
            self.assertIn(f"NY NOW 2026-11-01 01:30:00 {tz}", folded["clock_rows"][0])
            self.assertIn(f"Pull start 2026-11-01 01:30:00 {tz}", folded["clock_rows"][1])

    def test_daily_display_time_is_availability_not_actual_session_close(self):
        from pa_lens.terminal_monitor import clock_frame, format_tui
        boundary = "2026-11-18T00:00:00Z"
        native = {"status": "AVAILABLE_SOURCE_UNKNOWN", "ema20": {
            "status": "AVAILABLE_SOURCE_UNKNOWN", "value": "12.50", "effective_at": boundary}}
        daily = stream(boundary, native=native)
        daily["timeframe"] = "D"
        now = dt(boundary)
        view = TerminalMonitor(["SOXL"]).view({"streams": [daily]}, [], now=now, source=SRC)
        rendered = format_tui(clock_frame(view, now, "WAITING", now), width=80, height=24)
        self.assertIn("Daily bar available at", rendered)
        self.assertIn("2026-11-17 19:00:00 EST", rendered)
        self.assertIn("daily bar available at 2026-11-17 19:00:00 EST", view["text"])
        self.assertIn("Available at:", rendered)
        self.assertEqual(view["panels"]["NATIVE INDICATORS"][3:5],
                         ["Available at:", "2026-11-17 19:00:00 EST"])
        self.assertIn("available at 2026-11-17 19:00:00 EST", view["text"])

    def test_intraday_expanded_native_values_all_age_and_omission_is_provenance(self):
        from pa_lens.terminal_monitor import clock_frame
        def available(value, **fields):
            return dict(status="AVAILABLE_SOURCE_UNKNOWN", effective_at=T11, value=value, **fields)
        row = stream(T11, native=dict(status="AVAILABLE_SOURCE_UNKNOWN",
            ema20=available("10.5", relation="above", distance="0.5", atr_multiple="0.25"),
            vwap=available("11.2", relation="below"), atr14=available("2"), rsi14=available("60"),
            pivot_points=available("10.3", values=dict(pivot="10.3", r1="12.7", s1="9.2"))))
        receipt = dict(status="ELIGIBLE_OBSERVATIONS", quality={"omitted_emitted": 1})
        view = TerminalMonitor(["SOXL"]).view({"streams": [row]}, [(("SOXL",), receipt)], now=dt(T11), source=SRC)
        for expected in ("0.25 ATR", "EMA20", "VWAP", "below", "ATR14", "RSI14", "Pivot", "12.7"):
            self.assertIn(expected, view["text"])
        self.assertIn("Interp marker: omitted by provider", view["panels"]["DATA QUALITY"])
        self.assertEqual(view["risk"]["UNKNOWN"], 0)
        expired = clock_frame(view, dt("2026-11-18T15:14:00Z"), "WAITING", dt(T11))
        stale_rows = [label for label in expired["panels"]["NATIVE INDICATORS"] if "STALE (last pull)" in label]
        self.assertEqual(len(stale_rows), 4)
        for indicator in ("EMA20", "VWAP", "ATR14", "RSI14", "Pivot"):
            self.assertTrue(any(indicator in row for row in stale_rows))
        self.assertIn("12.7", " ".join(view["panels"]["NATIVE INDICATORS"]))
        self.assertNotIn("12.7", " ".join(expired["panels"]["NATIVE INDICATORS"]))

        receipt["omitted_emitted_by_symbol"] = {"SOXL": 1}
        bundled = TerminalMonitor(["SOXL", "SPY"]).view({"streams": [row, stream(T11, symbol="SPY")]},
            [(("SOXL", "SPY"), receipt)], now=dt(T11), source=SRC)
        self.assertEqual(bundled["panels"]["DATA QUALITY"].count("Interp marker: omitted by provider"), 1)

    def test_daily_native_and_market_stay_recent_until_expected_session(self):
        from pa_lens.terminal_monitor import clock_frame
        friday = "2026-11-13T21:00:00Z"
        native = dict(status="AVAILABLE_SOURCE_UNKNOWN", macd=dict(status="AVAILABLE_SOURCE_UNKNOWN",
            effective_at=friday, values=dict(macd="2", signal="1", histogram="1"), histogram_delta="0.5"))
        row = dict(stream(friday, native=native), timeframe="D")
        view = TerminalMonitor(["SOXL"]).view({"streams": [row]}, [], now=dt(friday), source=SRC)
        sunday = clock_frame(view, dt("2026-11-16T02:00:00Z"), "WAITING", dt(friday))
        self.assertEqual(sunday["risk"]["STALE"], 0)
        for value in ("MACD", "Sig", "Hist", "Delta"):
            self.assertIn(value, " ".join(sunday["panels"]["NATIVE INDICATORS"]))
        monday = clock_frame(view, dt("2026-11-16T23:01:00Z"), "WAITING", dt(friday))
        self.assertIn("MACD  STALE (last pull)", monday["panels"]["NATIVE INDICATORS"])

    def test_price_action_renders_active_setups_and_reference_coordinates(self):
        monitor = TerminalMonitor(["SOXL"])
        receipts = [(("SOXL",), {"status": "ELIGIBLE_OBSERVATIONS"})]
        candidate = dict(event("first", T10), status="candidate", anchors=dict(neckline=12))
        confirmed = dict(event("second", T11), anchors=dict(neckline=12, confirmation_level=12),
                         trigger=13, stop=9, target=15)
        baseline = monitor.view({"streams": [stream(T10, events=[candidate])]}, receipts, now=dt(T10), source=SRC)
        self.assertIn("Neckline 12", " ".join(baseline["panels"]["PRICE ACTION"]))
        row = stream(T11, events=[candidate, confirmed])
        row["summary"] = dict(regime=dict(efficiency_20=0.42, reference_atr=2),
            active_structures=dict(live_setups=[dict(family="double_bottom", status="confirmed", levels={}),
                                               dict(family="three_push_wedge", status="candidate", levels={})]),
            key_levels=[dict(label="SwLo", price=9), dict(label="PDH", price=13)])
        current = monitor.view({"streams": [row]}, receipts, now=dt(T11), source=SRC)
        for content in [current["text"], " ".join(current["panels"]["PRICE ACTION"])]:
            for field in ("NEW PA", "Neckline 12", "Trig 13", "Stop 9", "MM 15", "Confirm 12",
                          "Levels:", "SwLo 9", "PDH 13", "0.42", "three_push_wedge / candidate"):
                self.assertIn(field, content)
