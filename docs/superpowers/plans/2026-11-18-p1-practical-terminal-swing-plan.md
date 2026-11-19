# P1 Practical Terminal Monitor & Daily Swing Scanner Implementation Plan

> **Completed.** Tasks 1–5 shipped together. The steps below record the original implementation plan. See the [terminal guide](../../TERMINAL_MONITOR.md) for the current workflows.

**Goal:** Unblock default Robinhood OHLCV ingestion on omitted `interpolated` markers, align daily bars and native indicators to actual `XNYS` session closes with weekend-aware freshness, expand intraday/daily native indicator packs, and ship an upgraded live intraday TUI plus a one-shot `pa_lens swing` multi-ticker daily scanner.

**Architecture:** Keep the four causal PA detector engines (`core.py`, `advanced.py`, `observations.py`, `structures.py`) unchanged so pattern rules and knowledge-card SHA-256 mappings stay intact. Normalize timestamps, quality provenance, and multi-indicator native snapshots in the acquisition/interpretation layer, add a pure `StreamSummary` projection module (`pa_lens/context_summary.py`) for lifecycle resolution and key-level extraction, and wire both `TerminalMonitor` and the new `swing` CLI + `wizard` mode selector onto `StreamSummary`.

**Tech Stack:** Python 3.11+ (`../robinhood-trading-infra/.venv/bin/python`), `exchange-calendars==4.13.2`, `sqlite3`, `unittest`, zero new third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-11-18-p1-practical-terminal-swing-design.md`

## Global Constraints

- **Python interpreter for all test/CLI commands:** `../robinhood-trading-infra/.venv/bin/python` (has `exchange-calendars==4.13.2` installed).
- **Read-only MCP allowlist:** Only `get_equity_historicals`, `get_equity_quotes`, and `get_equity_technical_indicators` are permitted; native indicator budget `<= 64` calls per fetch/poll; zero order/account/credential access.
- **No silent fallback to local indicators:** Missing, mismatched, or stale native values must report `UNAVAILABLE` with explicit Chinese reason; local indicators remain labeled local/engine calculations.
- **Untouched detector files:** Do not modify `pa_lens/core.py`, `pa_lens/advanced.py`, `pa_lens/observations.py`, `pa_lens/structures.py`, or `pa_lens/replay.py` unless strictly unavoidable; `tests/test_knowledge.py` pins their `knowledge/concepts.json` SHA-256 digests.
- **Git workflow on `feature/p1-practical-terminal-swing`:** Commit only your task's intended files on the current feature branch (never touch `main`, never `git push`, never commit `local_data/` or `.superpowers/`), and end every git commit message with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Review Focus

1. **Mid-session `swing` / daily pull during market hours (e.g., `14:30 EST`):** Today's unfinished daily bar and unfinished daily native indicator point (`begins_at = todayT00:00:00Z`, `closed = today 16:00 EST`) must be excluded as `incomplete`, while yesterday's `16:00 EST` bar and native indicators match and stay `RECENT` (pinned in Task 1 & Task 3).
2. **Scheduled NYSE early-close session (`2026-11-27` Black Friday `13:00 EST` = `18:00 UTC`):** Pulling at `17:55 UTC` excludes Friday's daily bar as `incomplete`, while pulling at `18:05 UTC` emits Friday's daily bar and native indicator at `2026-11-27T18:00:00+00:00` (pinned in Task 1).
3. **Mixed batch containing both omitted `interpolated` and `interpolated: true`:** Explicit `interpolated: true` bars are rejected and `quality_status` degrades to `'PARTIAL_DATA'` (`ready=False`) rather than masking the interpolated gap behind `'ELIGIBLE_OBSERVATIONS'` (pinned in Task 2).
4. **Unavailable `ATR14` or single-point `MACD` snapshot:** Price overlays (`ema20`, `vwap`, `pivot_points`) still return `AVAILABLE_SOURCE_UNKNOWN` with `atr_multiple=None` (no division-by-zero/Decimal crash), and 1-point `macd` returns `AVAILABLE_SOURCE_UNKNOWN` with `histogram_delta=None` (pinned in Task 3).
5. **Confirmed setup later invalidated/reached by child `measured_move`:** When `measured_move` emits `invalidated` or `reached` with `parent_id` pointing to a `confirmed` `double_bottom` or `range_breakout`, `summarize_stream` moves that episode out of `live_setups` into `recent_resolved` instead of leaving a dead `Trig / Stop / MM` setup active (pinned in Task 4).

---

## File Map

- Modify `pa_lens/timeframes.py` — `daily_close`, dual-compatible `daily_session`, `consecutive_daily`, `is_daily_fresh`, `next_daily_close`.
- Modify `pa_lens/robinhood.py` — `strict_interpolation` default-accept omitted `interpolated` provenance; `XNYS` `daily_close` normalization for `interval == "day"`.
- Modify `pa_lens/provider_indicators.py` — `XNYS` `daily_close` normalization for `interval == "day"`.
- Modify `pa_lens/rh_runtime.py` — `source_identity`, `quality_status`, `acquire`, `aggregate_fifteen` omitted provenance, `next_poll_delay` `XNYS` daily close scheduling.
- Modify `pa_lens/native_runtime.py` — `context_specs` intraday 5-pack & daily 4-pack with in-place `output="last:2"` deduplication.
- Modify `pa_lens/native_interpretation.py` — multi-indicator pack interpretation (`ema20`, `vwap`, `atr14`, `rsi14`, `pivot_points`, `macd`), empty `returned_params` handling, ATR multiples, daily freshness.
- Create `pa_lens/context_summary.py` — pure `summarize_stream(...)` lifecycle resolver & key-level extractor.
- Modify `pa_lens/presentation.py` — promote `_STRUCTURAL_CANDIDATES` and `mtr_development`/`final_flag_development` closures to `priority=3`.
- Modify `pa_lens/service.py` — include `context_summary.py` in `CORE_SHA256`, stream retention (`bars=300`, `events=500`), `is_daily_fresh` in `snapshot()`, attach `summary=summarize_stream(...)`, clean omitted-marker readiness.
- Modify `pa_lens/dashboard.html` — multi-indicator `renderNativeContext` & NY session-date display for `16:00 ET` daily bars.
- Modify `pa_lens/terminal_monitor.py` — render expanded native indicators, active setup price coordinates, `Key Levels` strip, and `TuiClock.clock_frame` daily freshness + multi-row native stale aging.
- Create `pa_lens/swing.py` — `run_swing` & `format_swing_report` for `python -m pa_lens swing` (live Robinhood + offline `--input`).
- Modify `pa_lens/wizard.py` — top-level `monitor` vs `swing` mode prompt, remove `允许探索UNKNOWN？`.
- Modify `pa_lens/__main__.py` — register `swing` subcommand, add `--strict-interpolation` (retaining `--accept-unknown` as deprecated compatibility flag).
- Modify `README.md`, `README.zh-CN.md`, `docs/ROBINHOOD.md`, `docs/TERMINAL_MONITOR.md`, `docs/COVERAGE.md` — sync contracts and usage examples.

---

### Task 1: `XNYS` Session-Close Daily Semantics & Calendar-Aware Daily Freshness

**Files:**
- Modify: `pa_lens/timeframes.py`
- Modify: `pa_lens/robinhood.py:222-224,288-308`
- Modify: `pa_lens/provider_indicators.py:10,220-235`
- Modify: `pa_lens/rh_runtime.py:119-133`
- Test: `tests/test_daily.py`, `tests/test_provider_indicators.py`, `tests/test_rh_runtime.py`

**Interfaces:**
- Produces in `pa_lens/timeframes.py`:
  - `daily_close(session_label: str) -> datetime` — validates `calendar().is_session(session_label)` (exact `YYYY-MM-DD`), returns `calendar().session_close(session_label).to_pydatetime().astimezone(timezone.utc)`.
  - `daily_session(closed: datetime) -> str` — accepts canonical `XNYS` session close (`closed == daily_close(ny_label)` where `ny_label = closed.astimezone(ZoneInfo("America/New_York")).date().isoformat()`) AND legacy next-UTC-midnight (`closed.hour == closed.minute == closed.second == closed.microsecond == 0` where `(closed.date() - timedelta(days=1)).isoformat()` is an XNYS session); raises `ValueError` otherwise.
  - `consecutive_daily(old: datetime, new: datetime) -> bool` — returns `new > old and calendar().next_session(daily_session(old)).date().isoformat() == daily_session(new)`.
  - `is_daily_fresh(closed: datetime, now: datetime, grace_seconds: int = 7200) -> bool` — validates `daily_session(closed)`; returns `False` if `closed > now + timedelta(seconds=5)`; finds latest XNYS session whose `daily_close(s) + timedelta(seconds=grace_seconds) <= now` (checking `[now_ny_date - 14d .. now_ny_date]`) and returns `daily_session(closed) >= latest_required`.
  - `next_daily_close(now: datetime, settle_seconds: float = 10) -> float` — delay in seconds from `now` to the earliest upcoming `daily_close(session) + timedelta(seconds=settle_seconds)` strictly after `now`.

- [ ] **Step 1: Write failing tests in `tests/test_daily.py`, `tests/test_provider_indicators.py`, and `tests/test_rh_runtime.py`**

Add tests in `tests/test_daily.py` pinning:
```python
def test_xnys_session_close_early_close_and_intraday_cutoff(self):
    from datetime import datetime, timezone
    from pa_lens.timeframes import daily_close, daily_session, is_daily_fresh
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
```
Also update `tests/test_provider_indicators.py` daily timestamp expectations from `T00:00:00+00:00` (next midnight) to `XNYS` session close (`21:00:00+00:00` in EST / `20:00:00+00:00` in EDT) and add an `next_poll_delay(..., 'day', 10)` assertion in `tests/test_rh_runtime.py`.

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_daily tests.test_provider_indicators tests.test_rh_runtime -v`
Expected: FAIL with `ImportError: cannot import name 'daily_close'`

- [ ] **Step 3: Implement `timeframes.py` helpers and daily close normalization in `robinhood.py`, `provider_indicators.py`, and `rh_runtime.py`**

In `pa_lens/timeframes.py`: implement `daily_close`, `daily_session`, `consecutive_daily`, `is_daily_fresh`, and `next_daily_close`.
In `pa_lens/robinhood.py`: when `minutes is None` (`interval == "day"`), require `opened.hour == opened.minute == opened.second == opened.microsecond == 0`, compute `closed = daily_close(opened.date().isoformat())` (counting `local["invalid"] += 1` if non-midnight or non-XNYS session), and check `if cutoff < closed: local["incomplete"] += 1; continue`.
In `pa_lens/provider_indicators.py`: when `interval == "day"`, require `opened` at `00:00:00Z` and set `closed = daily_close(opened.date().isoformat())` before `if closed > cutoff`.
In `pa_lens/rh_runtime.py`: in `next_poll_delay`, delegate `interval == 'day'` after `settle_seconds` validation to `next_daily_close(now, settle_seconds)`.

- [ ] **Step 4: Run targeted tests and existing daily/audit tests**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_daily tests.test_provider_indicators tests.test_rh_runtime tests.test_robinhood tests.test_audit -v`
Expected: PASS (updating any existing daily mock timestamps in `tests/test_robinhood.py` that asserted next-UTC-midnight on `RobinhoodProvider.fetch(..., interval="day")`).

---

### Task 2: Omitted `interpolated` Default Acceptance & Readiness Unblocking

**Files:**
- Modify: `pa_lens/robinhood.py:203-233,276-326`
- Modify: `pa_lens/rh_runtime.py:11-50,78-117`
- Modify: `pa_lens/service.py:145-169,349-435`
- Test: `tests/test_robinhood.py`, `tests/test_rh_runtime.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `timeframes.is_daily_fresh` from Task 1.
- Produces:
  - `RobinhoodProvider.fetch(self, symbols, start, end, *, interval="minute", bounds="regular", adjustment_type="split", strict_interpolation=False) -> FetchResult`
    - Validation: `if type(strict_interpolation) is not bool: raise ValueError("strict_interpolation must be a boolean")`.
    - When `"interpolated" not in item`: `local["interpolation_omitted"] += 1` and record open timestamp in `quality["interpolation_omitted_opens"]` (`quality["interpolation_unknown"]` stays `0`). If `strict_interpolation` is `True`: reject (`source` appends `:strict_interpolation`). Else: emit bar with provenance `{"interpolation": "omitted", "quality": "INTERPOLATION_OMITTED"}`, increment `local["emitted"]` and `local["omitted_emitted"]`, canonical `source = f"robinhood:{interval}:{bounds}:{adjustment_type}"`.
    - When `"interpolated" in item and type(item["interpolated"]) is not bool`: `local["invalid"] += 1`, always rejected.
    - When `item.get("interpolated") is True`: `local["interpolated"] += 1`, always rejected.
  - `rh_runtime.source_identity(interval, bounds='regular', adjustment_type='split', strict_interpolation=False) -> str` — appends `:strict_interpolation` only when `strict_interpolation` is `True`.
  - `rh_runtime.acquire(provider, journal, symbols, start, end, *, interval='minute', bounds='regular', adjustment_type='split', strict_interpolation=False, capture_dir=None, include_quotes=False)` — forwards `strict_interpolation`.
  - `rh_runtime.quality_status(quality) -> str`:
    - If `quality.get('strict_interpolation') and quality.get('interpolation_omitted') and not quality.get('emitted')`: `'NO_USABLE_BARS'`
    - If `quality.get('interpolation_unknown', 0)`: `'DATA_QUALITY_UNKNOWN'`
    - If `not quality.get('emitted', 0)`: `'NO_USABLE_BARS'`
    - If `any(quality.get(k) for k in ('invalid','interpolated','missing_results','no_usable_symbols','out_of_range','incomplete_derived_buckets'))`: `'PARTIAL_DATA'`
    - Else: `'ELIGIBLE_OBSERVATIONS'`
  - `Journal.snapshot()` uses `is_daily_fresh(_datetime(last['time']), now)` when `timeframe == 'D'` and retains `deque(maxlen=300)` bars and `deque(maxlen=500)` events per stream.

- [ ] **Step 1: Write failing tests in `tests/test_robinhood.py` and `tests/test_rh_runtime.py`**

Update/add tests in `tests/test_robinhood.py` and `tests/test_rh_runtime.py`:
- `test_omitted_interpolation_accepted_by_default_and_rejected_when_strict`: omitted `"interpolated"` emits bar by default with `provenance["interpolation"] == "omitted"`, `provenance["quality"] == "INTERPOLATION_OMITTED"`, `source == "robinhood:minute:regular:split"`, and `strict_interpolation=True` emits `0` bars.
- `test_malformed_or_true_interpolation_always_rejected_and_marks_partial`: batch with 1 omitted bar + 1 `interpolated: True` bar emits 1 bar, sets `quality["interpolated"] == 1`, and `rh_runtime.quality_status(result.quality) == "PARTIAL_DATA"` (`Journal.snapshot(NOW)["ready"] is False`); `interpolated: None` increments `invalid` and is rejected even when `strict_interpolation=False`.
- `test_omitted_markers_achieve_ready_for_research_when_warm`: ingesting 5+ sequential bars with omitted `"interpolated"` via `rh_runtime.acquire` yields `snap["ready"] is True`, `snap["readiness"] == "READY_FOR_RESEARCH"`, and derived `15minute` triples propagate `"interpolation": "omitted"` with `ELIGIBLE_OBSERVATIONS`.

- [ ] **Step 2: Run tests to verify failure**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_robinhood tests.test_rh_runtime tests.test_service -v`
Expected: FAIL (omitted bars currently rejected by default and marked `DATA_QUALITY_UNKNOWN`).

- [ ] **Step 3: Implement omitted-marker policy in `robinhood.py`, `rh_runtime.py`, and `service.py`**

Update `RobinhoodProvider.fetch`, `rh_runtime.source_identity`, `rh_runtime.quality_status`, `rh_runtime.acquire`, `rh_runtime.aggregate_fifteen`, and `Journal` (`_new` retention `bars=300, events=500`, `_acquisitions` pop `interpolation_omitted_opens`, `snapshot` daily freshness via `is_daily_fresh` and updated Chinese `notice`).

- [ ] **Step 4: Run tests to verify pass**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_robinhood tests.test_rh_runtime tests.test_service -v`
Expected: PASS.

---

### Task 3: Expanded Native Indicator Context Packs (`EMA20 / VWAP / ATR14 / RSI14 / Pivot / MACD`)

**Files:**
- Modify: `pa_lens/native_runtime.py:122-129`
- Modify: `pa_lens/native_interpretation.py`
- Modify: `pa_lens/dashboard.html:30-38,77-97`
- Test: `tests/test_native_interpretation.py`, `tests/test_native_runtime.py`, `tests/test_panel.py`

**Interfaces:**
- Consumes: `timeframes.is_daily_fresh`, `timeframes.daily_session` from Task 1.
- Produces:
  - `native_runtime.context_specs(specs, interval='5minute', enabled=True, bounds='regular') -> list[dict]`:
    - Returns `list(specs)` unchanged when `not enabled` or `interval == '15minute'` or `bounds not in ('regular', 'extended')` or `interval not in (*INTRADAY_SECONDS, 'day')`.
    - Intraday pack (`interval in ('minute','5minute','10minute','30minute','hour','4hour')`):
      `[('ema', {'period': 20}), ('vwap', {}), ('atr', {'period': 14}), ('rsi', {'period': 14}), ('pivot_points', {'method': 'classic'})]`, each with `output='last:2'`.
    - Daily pack (`interval == 'day'` and `bounds == 'regular'`):
      `[('ema', {'period': 20}), ('atr', {'period': 14}), ('rsi', {'period': 14}), ('macd', {'fast_period': 12, 'slow_period': 26, 'signal_period': 9})]`, each with `output='last:2'`.
    - Deduplication: effective params of an existing spec `s` is `{**INDICATOR_DEFAULTS[s['type']], **s['parameters']}`. If an existing spec matches `(name, interval, effective_params)`, do not append a duplicate; if its `output == 'latest'`, upgrade `s['output'] = 'last:2'` in place (leave `'series'` or `'last:N'` with `N >= 2` untouched).
  - `native_interpretation.interpret(bar, snapshots, now, observation_seq, historical=False, bar_quality=None) -> dict`:
    - Pack keys evaluated for intraday: `('ema20', 'vwap', 'atr14', 'rsi14', 'pivot_points')`; for daily: `('ema20', 'atr14', 'rsi14', 'macd')` (if `semantics` is False, e.g. `15m` or manual source, populate `'ema20'` and `'rsi14'` as `UNAVAILABLE` for backward compatibility).
    - Parameter check: for `vwap` (`{}`) and `pivot_points` (`{'method': 'classic'}`), accept `returned_params == {}` or `{'method': 'classic'}` as long as `requested['parameters']` has no conflicting override; for `ema`/`atr`/`rsi`, require effective requested & returned `period` match; for `macd`, require `(fast_period, slow_period, signal_period) == (12, 26, 9)`.
    - Freshness check: `not is_daily_fresh(point, now)` when `interval == 'day'`, else `(now - point).total_seconds() > max(120, seconds * 2)`.
    - First evaluate `atr14` so `atr_dec` (`Decimal` > 0 if available, else `None`) is known.
    - Single-value indicators (`ema20`, `vwap`, `atr14`, `rsi14`): set `value=str(val)`. For price overlays (`ema20`, `vwap`), set `relation` (`'above'|'below'|'equal'`), `distance=str(close - val)`, and `atr_multiple=str(((close - val) / atr_dec).quantize(Decimal('0.01')))` if `atr_dec` else `None`.
    - `pivot_points`: parse all 7 fields `('pivot','r1','r2','r3','s1','s2','s3')` as finite `Decimal` strings into `values={...}`, `value=values['pivot']`, `relation` vs `pivot`, `distance=str(close - pivot_dec)`, `atr_multiple` if `atr_dec` else `None`.
    - `macd`: parse `('macd','signal','histogram')` as finite `Decimal` strings into `values={...}`, `value=values['histogram']`; if `len(row.get('points', ())) >= 2` and `row['points'][-1]['time'] == latest['time']` and `row['points'][-2]['values'].get('histogram') is not None`, compute `histogram_delta = str(Decimal(values['histogram']) - Decimal(row['points'][-2]['values']['histogram']))`, else `histogram_delta = None`.
    - Overall `base['status']`: `'AVAILABLE_SOURCE_UNKNOWN'` if all pack keys for the interval are available, `'PARTIAL_NATIVE_CONTEXT'` if `1 <= available < len(pack_keys)`, `'UNAVAILABLE'` if `0`.

- [ ] **Step 1: Write failing tests in `tests/test_native_interpretation.py`**

Add/update tests in `tests/test_native_interpretation.py`:
- Intraday `context_specs([], interval='5minute')` returns the 5-indicator pack (`ema20, vwap, atr14, rsi14, pivot_points`) with `output='last:2'`; `context_specs(native_specs('all', None, '5minute', 'latest'), interval='5minute')` still has length `18` with upgraded `output='last:2'` on the 5 context slots; daily `context_specs([], interval='day')` returns the 4-indicator pack (`ema20, atr14, rsi14, macd`).
- Intraday `interpret()` handles empty `returned_params={}` on `vwap` and `pivot_points`, computes `distance` & `atr_multiple` when `atr14` is available, and sets `atr_multiple=None` cleanly when `atr14` is `UNAVAILABLE`.
- Daily `interpret()` on Sunday evening (`now = 2026-11-23T01:00:00Z`, Friday `bar['time'] = '2026-11-20T21:00:00+00:00'`) keeps `ema20`, `atr14`, `rsi14`, and `macd` `AVAILABLE_SOURCE_UNKNOWN`, computes `histogram_delta` when 2 points exist, and sets `histogram_delta=None` when only 1 point exists.

- [ ] **Step 2: Run tests to verify failure**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_native_interpretation tests.test_native_runtime tests.test_panel -v`
Expected: FAIL (only `ema20`/`rsi14` currently requested and interpreted; daily Friday snapshot marked expired after 48h).

- [ ] **Step 3: Implement `context_specs`, `interpret`, and `dashboard.html` native rendering**

Update `pa_lens/native_runtime.py`, `pa_lens/native_interpretation.py`, and `pa_lens/dashboard.html` (updating `chartDescription` daily NY date string to format `America/New_York` calendar date rather than `stamp - 86400000`, and `renderNativeContext` to loop across present pack keys including `vwap`, `atr14`, `pivot_points`, and `macd`).

- [ ] **Step 4: Run tests to verify pass**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_native_interpretation tests.test_native_runtime tests.test_panel -v`
Expected: PASS.

---

### Task 4: Unified `StreamSummary` Projection (`pa_lens/context_summary.py`) & Candidate Priority

**Files:**
- Create: `pa_lens/context_summary.py`
- Modify: `pa_lens/presentation.py:13-31`
- Modify: `pa_lens/service.py:27-33,410-420`
- Create: `tests/test_context_summary.py`
- Modify: `tests/test_presentation.py`

**Interfaces:**
- Consumes: `native_interpretation` dict from Task 3, `Engine.snapshot()` and `Bar`/event dicts from `Journal`.
- Produces in `pa_lens/context_summary.py`:
  - `summarize_stream(bars: Sequence[dict], events: Sequence[dict], engine_state: dict, native_interpretation: dict | None = None, *, focus_bars: int | None = None) -> dict`:
    - `regime`: `{"context": str, "efficiency_20": float, "bars_total": int, "bars_in_segment": int, "focus_window_bars": int, "engine_atr": float | None, "reference_atr": float | None, "atr_origin": "robinhood_native_atr14" | "local_engine_atr15" | None}`.
    - `native_summary`: detached summary of available pack indicators from `native_interpretation` (`status`, `items`: ordered list of `{key, label, status, display_value, relation, distance, atr_multiple, reason}`).
    - `active_structures`:
      - Resolves episodes across `events`:
        - Multi-stage setups (`double_bottom`, `double_top`, `three_push_wedge`, `failed_failure`, `opening_reversal`, `mtr_development`, `final_flag_development`): group by `root_id = event['id']` for roots (`parent_id` absent or not a setup root) and `event['parent_id']` for children (`trend_line_retest` also attaches to its `mtr_development` root). Latest event in each episode determines current status (`candidate`, `confirmed`, `invalidated`, `expired`, `observed`).
        - Child `measured_move` (`reached` / `invalidated`) whose `parent_id` matches a `confirmed` `double_bottom` / `double_top` / `range_breakout`: updates that parent episode's `target_state` to `'reached'` or `'invalidated'`. If `target_state == 'invalidated'`, the parent episode's effective status becomes `'invalidated'` (moved out of `live_setups` into `recent_resolved`); if `'reached'`, it moves to `recent_resolved` with `status='reached'`.
      - `live_setups`: episodes whose latest observation falls within the last `focus_window_bars` bars (default `min(len(bars), focus_bars or 30)`) and whose effective status is `'candidate'` or `'confirmed'` (or `'observed'` for `high_attempt` / `low_attempt` / `trend_line_retest`), restricted to actionable families `{'double_bottom','double_top','three_push_wedge','range_breakout','breakout_observation','failed_breakout','failed_failure','opening_reversal','opening_breakout_mode','mtr_development','final_flag_development','tight_channel','high_attempt','low_attempt'}`. Each item has `{"id", "family", "status", "direction", "observed_at", "stage", "levels": {...}, "explanation"}` where `levels` normalizes non-null coordinates from `event` & `anchors` (`neckline`, `confirmation_level`, `invalidation_extreme`, `line_value`, `trigger`, `stop`, `target`, `range_high`, `range_low`, `signal_bar_extreme`).
      - `recent_resolved`: episodes resolved (`invalidated`, `expired`, `reached`) within the last `min(5, focus_window_bars)` bars.
    - `key_levels`: sorted descending by `price`, deduplicated within `(kind, round(price, 4))`, collecting:
      - Latest confirmed 2-left/2-right swing high (`SwHi`) and swing low (`SwLo`) computed causally from `bars` (`bars[:-2]` center check matching `Engine`).
      - Prior session high/low: for `timeframe == 'D'` with `len(bars) >= 2`, `PrevDayHi` / `PrevDayLo` from `bars[-2]`; for intraday when `bars` include the prior NY date's bars, `PDH` / `PDL`.
      - 20-bar range bounds (`20B Hi`, `20B Lo`) when `len(bars) >= 20`.
      - Active setup coordinates (`Neckline`, `Confirm`, `Trig`, `Stop`, `MM`) from `live_setups`.
      - Available native price overlays (`EMA20`, `VWAP`, `Pivot P`, `R1`, `S1`).
      - Each entry: `{"kind": str, "label": str, "price": float, "distance": float, "atr_multiple": float | None, "source": "structure" | "swing" | "native"}`.
    - `htf_alignment`: `None`.
- Produces in `pa_lens/presentation.py`:
  - `_STRUCTURAL_CANDIDATES = {'double_bottom', 'double_top', 'three_push_wedge', 'opening_reversal', 'opening_breakout_mode', 'mtr_development', 'final_flag_development'}`
  - `priority(event)` returns `3` if `event['family'] in _STRUCTURAL_CANDIDATES and event['status'] in ('candidate', 'confirmed', 'invalidated', 'reached', 'expired')` (keeping `failed_failure` candidate at `2` and `_BASIC` at `0`).
- Produces in `pa_lens/service.py`:
  - `'context_summary.py'` added to `_code_hash` list; `Journal.snapshot()` includes `'summary': summarize_stream(stream['bars'], stream['events'], state, native_interp)` on every stream dict.

- [ ] **Step 1: Write failing tests in `tests/test_context_summary.py` and `tests/test_presentation.py`**

Create `tests/test_context_summary.py` testing:
1. `double_bottom` `candidate` -> `confirmed` -> `measured_move` `invalidated` lifecycle transitions: at `candidate` bar, `live_setups` shows `double_bottom / candidate` with `neckline`; at `confirmed` bar, `live_setups` shows `double_bottom / confirmed` with `trigger / stop / target` (and old candidate is NOT duplicated); when child `measured_move` (`parent_id = confirmed['id']`) emits `invalidated`, `live_setups` is empty and `recent_resolved` holds the invalidated setup!
2. 3-stage `final_flag_development` (`late_consolidation` -> `continuation_breakout` -> `breakout_failed`, sharing root `parent_id`): resolves to single episode at stage `'breakout_failed'`.
3. `key_levels` extracts `SwHi`, `SwLo`, `PrevDayHi/Lo` on daily bars, `20B Hi/Lo`, structural `Neckline/Trig/Stop/MM`, and native `EMA20/Pivot` sorted descending with finite `distance` and `atr_multiple`.
4. Prefix determinism: `summarize_stream` does not mutate input `bars` or `events`, and `htf_alignment` is `None`.
Add test in `tests/test_presentation.py` verifying `priority=3` for `double_bottom` / `opening_reversal` / `mtr_development` candidates while `test_confirmed_failed_failure_is_key_change_but_candidate_not` still passes.

- [ ] **Step 2: Run tests to verify failure**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_context_summary tests.test_presentation -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'pa_lens.context_summary'`).

- [ ] **Step 3: Implement `pa_lens/context_summary.py`, update `pa_lens/presentation.py` and `pa_lens/service.py`**

Implement `summarize_stream` in `pa_lens/context_summary.py`, update `priority()` in `pa_lens/presentation.py`, and attach `summary` + `CORE_SHA256` entry in `pa_lens/service.py`.

- [ ] **Step 4: Run tests to verify pass**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_context_summary tests.test_presentation tests.test_service -v`
Expected: PASS.

---

### Task 5: Practical Intraday TUI Upgrade, `pa_lens swing` CLI, Wizard & Documentation

**Files:**
- Create: `pa_lens/swing.py`
- Modify: `pa_lens/terminal_monitor.py`
- Modify: `pa_lens/wizard.py`
- Modify: `pa_lens/__main__.py`
- Modify: `README.md`, `README.zh-CN.md`, `docs/ROBINHOOD.md`, `docs/TERMINAL_MONITOR.md`, `docs/COVERAGE.md`
- Create: `tests/test_swing.py`
- Modify: `tests/test_terminal_monitor.py`, `tests/test_wizard.py`, `tests/test_cli.py`, `tests/test_rh_runtime.py`, `tests/test_native_interpretation.py`

**Interfaces:**
- Consumes: `StreamSummary` (`stream["summary"]`), `is_daily_fresh`, `strict_interpolation`, expanded `context_specs` & `native_interpretation`.
- Produces:
  - `TerminalMonitor` (`pa_lens/terminal_monitor.py`):
    - Renders expanded native rows (`EMA20` with relation & ATR diff, `VWAP` with relation, `ATR14` + `RSI14`, `Pivot P/R1/S1` or `MACD/Sig/Hist/Delta`), registering every numeric row `(row_index, label)` in `clock_slots` `native_rows` so `clock_frame` overwrites all of them with `<label>  <freshness> (last pull)` when stale.
    - `clock_slots` tuple includes `daily: bool` so `clock_frame` uses `is_daily_fresh(close, now)` when `daily=True` instead of `age > limit`.
    - `PRICE ACTION` panel renders `context` + efficiency, formats level coordinates (`Neckline`, `Trig`, `Stop`, `MM`, `Confirm`) on `NEW PA` / `HISTORY` events, lists up to 3 active setups from `stream.get("summary", {}).get("active_structures", {}).get("live_setups", ())`, and appends a compact `Levels:` line (`SwHi`, `SwLo`, `PDH/PDL` or `20B Hi/Lo`).
    - Data Quality panel shows `Interp marker: omitted by provider` when `omitted_emitted > 0` without raising `risk["UNKNOWN"]`.
  - `pa_lens/swing.py`:
    - `run_swing(args, parser) -> int`
    - `format_swing_report(streams: Sequence[dict], *, now: datetime, focus_bars: int, warmup_days: int | None = None) -> str`
    - CLI subcommand `python -m pa_lens swing`:
      - `--symbols` (`nargs='+'`, default `['SPY', 'QQQ', 'NVDA']`)
      - `--warmup-days` (`int`, default `250`, range `60..1825`)
      - `--focus-bars` (`int`, default `25`, range `5..120`)
      - `--input` (`str`, optional offline daily JSONL/CSV path; partitions multi-symbol rows by `(symbol, timeframe, source)`, requires `timeframe == 'D'`, filters by `--symbols` only if `--symbols` was explicitly supplied)
      - `--adjustment` (`choices=['none','split','all']`, default `'split'`)
      - `--strict-interpolation` (`action='store_true'`)
      - `--no-native-context` (`action='store_true'`)
      - `--infra-root`, `--codex-binary` (`default='codex'`), `--timeout` (`default=30.0`), `--db` (`default=':memory:'`), `--capture-dir`, `--output` (`choices=['text','jsonl']`)
  - `pa_lens/wizard.py`:
    - First prompt: `模式 monitor（盘中/实时监控）/ swing（日K波段扫描） [monitor]` (`choice(('monitor', 'swing', '1', '2'))`, mapping `'1' -> 'monitor'`, `'2' -> 'swing'`).
    - `monitor` branch: removes `允许探索UNKNOWN？` prompt; builds `poll-robinhood` argv without `--accept-unknown`.
    - `swing` branch: prompts for `股票` (`default='SPY QQQ NVDA'`), `暖机自然日 60..1825` (`default='250'`), `聚焦最近交易日数 5..120` (`default='25'`), and `Robinhood infra 根目录`, previews `python -m pa_lens swing ...`, confirms `yes/no`, and invokes `runner(argv)`.
  - `pa_lens/__main__.py`:
    - Adds `--strict-interpolation` (`action='store_true'`) to `fetch-robinhood` and `poll-robinhood` while keeping `--accept-unknown` (`action='store_true'`, deprecated compatibility flag) and wiring `strict_interpolation=args.strict_interpolation` into `acquire` / `source_identity`.

- [ ] **Step 1: Write failing tests in `tests/test_swing.py`, `tests/test_terminal_monitor.py`, and `tests/test_wizard.py`**

Create `tests/test_swing.py`:
- Offline multi-symbol daily JSONL input (`NVDA` + `QQQ`, 40 consecutive XNYS sessions ending with a double-bottom confirmation) via `main(['swing', '--input', path, '--focus-bars', '15', '--output', 'text'])` and `'--output', 'jsonl'`: verifies warmup bar count, focus window, regime, active `double_bottom`, `Neckline / Trig / Stop / MM` reference coordinates, `PrevDayHi/Lo`, and `probability=None` research-only disclaimer.
- Mocked live Robinhood `swing --symbols NVDA --warmup-days 250 --focus-bars 25 --output text`: verifies `interval='day'`, `bounds='regular'`, 4-pack daily native indicators (`EMA20`, `ATR14`, `RSI14`, `MACD`), and clean `:memory:` execution without leaving SQLite files on disk.
Update/add tests in `tests/test_terminal_monitor.py`:
- Intraday 5-pack native rendering + `clock_frame` aging all 5 rows (`EMA20`, `VWAP`, `ATR14`, `RSI14`, `Pivot`) to `STALE (last pull)` after intraday limit, while daily `clock_frame` keeps Friday `16:00 EST` `RECENT` on Sunday night!
- Structural candidate (`double_bottom / candidate`) and confirmed setup coordinates (`neckline`, `Trig`, `Stop`, `MM`) rendered in `PRICE ACTION` panel.
Update `tests/test_wizard.py`:
- Test `monitor` flow (without `允许探索UNKNOWN？` prompt) and `swing` flow (`swing --symbols SPY QQQ NVDA --warmup-days 250 --focus-bars 25 ...`).

- [ ] **Step 2: Run tests to verify failure**

Run: `../robinhood-trading-infra/.venv/bin/python -m unittest tests.test_swing tests.test_terminal_monitor tests.test_wizard -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'pa_lens.swing'`, missing TUI fields, old wizard prompt count).

- [ ] **Step 3: Implement `pa_lens/swing.py`, upgrade `terminal_monitor.py`, `wizard.py`, `__main__.py`, and sync docs**

Implement `pa_lens/swing.py`, update `pa_lens/terminal_monitor.py`, `pa_lens/wizard.py`, `pa_lens/__main__.py` (also updating `tests/test_native_interpretation.py`'s `test_cli_default_requests_native20_14_and_optout_does_not` to assert the 5-indicator intraday pack on `5minute`), and update `README.md`, `README.zh-CN.md`, `docs/ROBINHOOD.md`, `docs/TERMINAL_MONITOR.md`, and `docs/COVERAGE.md` to reflect:
- Default acceptance of omitted `interpolated` markers (`--strict-interpolation` opt-in);
- `XNYS` `16:00 ET` / early-close daily timestamps & calendar-aware freshness;
- Intraday 5-pack & daily 4-pack automatic native context;
- `python -m pa_lens swing` & `wizard` mode selection;
- Browser canvas level overlays explicitly noted as future TODO.

- [ ] **Step 4: Run full verification suite, knowledge check, compilation, and diff check**

Run:
```bash
../robinhood-trading-infra/.venv/bin/python -m compileall -q pa_lens tests knowledge
../robinhood-trading-infra/.venv/bin/python -m unittest discover -s tests -v
../robinhood-trading-infra/.venv/bin/python knowledge/kb.py search "双底" >/dev/null
git diff --check
```
Expected: All tests PASS (1 optional Chromium screenshot test skipped if Chromium binary absent), zero `kb` / `knowledge` hash errors, zero whitespace errors.
