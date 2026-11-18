# P1 Design: Practical Terminal Monitor & Daily Swing Scanner

Date: 2026-11-18
Status: Ready for User Approval (Builder Check Completed)
Scope: Phase 1 (Single-Timeframe Practical Base & Terminal Workflows; Phase 2 Multi-Timeframe `--htf/--ltf` Alignment and Browser Canvas Level Overlays are deferred)

---

## 1. Intent and Why

`pa_lens` v0.7 has a strong causal, read-only, revision-aware Price Action (PA) and native Robinhood MCP foundation, but four overly conservative or incomplete contracts prevent practical daily trading observation:

1. **Default 100% bar rejection on omitted `interpolated`**: Recent Robinhood historical OHLCV responses use `omitempty` semantics—emitting `"interpolated": true` on synthetic/interpolated bars (such as 3-month-old minute bars) while omitting the `"interpolated"` key on genuine recent intraday and daily bars. Treating key omission as unusable causes `0` emitted bars by default, and `--accept-unknown` permanently locks `ready=false` while raising `RISK: UNKNOWN` alarms in the TUI.
2. **Artificial next-UTC-midnight delay on daily bars**: Normalizing daily session availability to `00:00 UTC` the next day (19:00 EST / 20:00 EDT) discards today's completed daily bar after the 16:00 ET NYSE close, while the naive 48-hour freshness window marks Friday's daily bar and native indicators `STALE` on Sunday evening and 3-day holiday weekends.
3. **Silent structural candidates and missing reference prices in TUI**: Key developing structures (`double_bottom`, `double_top`, `three_push_wedge`, `opening_reversal`, `mtr_development`, `final_flag_development`) are hidden at default priority `3` (indeed `opening_reversal` and `mtr_development` never emit `confirmed` at all), TUI panels omit computed structural levels (`neckline`, `trigger`, `stop`, `target`, swing highs/lows), and native context only fetches `EMA20` and `RSI14`—missing intraday `VWAP`, `ATR14`, `Pivot Points`, and daily `MACD`.
4. **Disconnected daily Swing workflow**: Evaluating ~1 month of daily PA requires ~6 months of prior daily bars for 20-bar context/range windows and 5-pivot swing/wedge warmup, plus matching daily native indicators and extracted reference levels (`buy stop` / `buy limit` observation levels and invalidation stops) in one terminal command.

Phase 1 turns `pa_lens` into a practical, terminal-first observation assistant for two workflows:
- **Intraday live TUI monitoring** (e.g., 5-minute regular-session TUI at market open to observe entries, exits, key levels, and native `EMA20 / VWAP / ATR14 / RSI14 / Pivot Points`).
- **One-shot Daily Swing terminal scanning** (`pa_lens swing`, also accessible from `wizard`) across 1–10 tickers, warming up on ~6 months of daily bars and summarizing the recent ~1 month of trend context, reversal/pullback structures, and objective reference levels.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- Accept Robinhood OHLCV bars with omitted `interpolated` by default while continuing to hard-reject `interpolated: true` and malformed/`null` `interpolated` values, recording exact provenance (`"omitted"` vs `"explicit_false"`) without locking `ready=false` or triggering TUI `UNKNOWN` risk alerts.
- Normalize Robinhood daily bar and daily native indicator close timestamps to actual `XNYS` regular session close (`16:00 ET`, or `13:00 ET` on scheduled early-close sessions) via `exchange_calendars`, with calendar-aware daily freshness across weekends and market holidays.
- Expand automatic native indicator context packs:
  - Intraday (`minute`, `5minute`, `10minute`, `30minute`, `hour`, `4hour` in `regular`/`extended` bounds): `EMA20`, `VWAP`, `ATR14`, `RSI14`, `Pivot Points (classic)`.
  - Daily (`day`, `regular` bounds): `EMA20`, `ATR14`, `RSI14`, `MACD (12, 26, 9)`.
- Introduce a pure, deterministic `StreamSummary` projection layer (`pa_lens/context_summary.py`) that distills regime, native indicator distances (in points and ATR multiples), lifecycle-resolved active structures, and objective key levels (`swing high/low`, `prior session high/low`, `range high/low`, `neckline`, `trigger`, `stop`, `MM target`).
- Upgrade `terminal_monitor.py` (both TUI and text modes) to display the expanded native indicator pack, actionable structural candidates, and structural/swing key levels without weakening existing `STALE`, `QUARANTINE`, `FIXED END`, or baseline anti-promotion safeguards.
- Add `python -m pa_lens swing` (and a top-level mode choice in `wizard`) for multi-symbol daily Swing terminal scanning, supporting both live Robinhood read-only acquisition and offline JSONL/CSV input.
- Reserve a clean `htf_alignment` extension slot on `StreamSummary` so Phase 2 (`--htf` / `--ltf` 4-state alignment verdict) plugs in without schema churn.

### Non-Goals (Deferred)
- **Phase 2 Multi-Timeframe (`--htf` / `--ltf`) joint execution & 4-state alignment verdict**: Deferred to Phase 2.
- **Browser `dashboard.html` canvas price-level / trendline overlays**: Deferred as a future TODO (`dashboard.html` remains functional and compatible with updated snapshot payloads).
- **New discretionary PA detectors** (`second-leg-trap`, `parabolic-wedge`, `always-in`) or independent human ground-truth calibration campaigns.

### Anti-Goals (Must Never Happen)
- **No order execution, brokerage account reads, credential storage, or autonomous trade recommendations**: Reference levels (`trigger`, `stop`, `target`, `neckline`) remain objective structural coordinates with `probability=None`, never imperative buy/sell instructions.
- **No silent fallback from native indicators to local indicators**: When native values are missing, mismatched, or stale, report them unavailable explicitly; local `EMA20 / RSI14 / engine ATR` stay labeled as local/engine calculations.
- **No lookahead or silent history rewriting**: Unclosed intraday or daily bars are never emitted; revisions and late arrivals remain quarantined.
- **No acceptance of `interpolated: true`**: Explicitly interpolated bars (such as historical 3-month-old minute bars) are always rejected.

---

## 3. Constraints

- **Read-only MCP allowlist**: Only `get_equity_historicals`, `get_equity_quotes`, and `get_equity_technical_indicators` may be called via `CodexMarketTransport`. Native indicator budget stays `<= 64` calls per poll/fetch.
- **Journal code identity**: Modules participating in `service.CORE_SHA256` (`context_summary.py` will be added to the hash list) pin SQLite journal identity; existing local databases fail closed and new runs use fresh database paths as already enforced by `Journal` and `wizard`.
- **Causal prefix invariance**: `Engine` and `PresentationProjector` prefix consistency tests must remain 100% green.
- **Data hygiene**: Raw market captures and SQLite files remain restricted to git-ignored `local_data/` or `:memory:`.

---

## 4. Approaches Considered

### Approach A (Selected): Unified `StreamSummary` Projection Layer (`pa_lens/context_summary.py`)
Keep the four causal detector modules (`core.py`, `advanced.py`, `observations.py`, `structures.py`) unchanged in their mathematical detection rules, and build a pure projection module `pa_lens/context_summary.py` on top of stream bars, raw/display events, engine snapshot, and `native_interpretation`. Both the upgraded live `TerminalMonitor` and the new `swing` CLI command consume `StreamSummary`.
- **Pros**: Single source of truth for lifecycle resolution (`candidate` -> `confirmed` / `invalidated` / `expired` via `parent_id`), price-level extraction, and ATR-distance formatting; zero duplication between intraday TUI and daily Swing cards; Phase 2 MTF alignment simply becomes `align(htf_summary, ltf_summary)`.
- **Trade-off**: Adds one focused ~180-line domain module and unit tests.

### Approach B (Rejected): Inline TUI String Formatting + Standalone `swing` Script
Format `anchors` dictionaries directly inside `terminal_monitor.py` and write a separate `swing` script with its own level/candidate extraction.
- **Cons**: Duplicates anchor parsing across 10+ event families in two places, risks divergent level numbers between intraday TUI and daily Swing output, and requires refactoring before Phase 2 MTF linkage.

---

## 5. Detailed Design

### 5.1 Interpolation Omission Policy (`robinhood.py`, `rh_runtime.py`, `service.py`, `terminal_monitor.py`, `wizard.py`, `__main__.py`)

1. **`RobinhoodProvider.fetch` parameter**:
   - Add `strict_interpolation: bool = False` (default `False`). Retain `accept_unknown: bool | None = None` as a deprecated compatibility alias: if a caller explicitly passes `accept_unknown=False` without setting `strict_interpolation`, wait—to avoid breaking callers while switching the default cleanly:
     - Let `fetch(..., strict_interpolation=False, accept_unknown=None)`: if `accept_unknown is not None`, `strict = not accept_unknown` (preserving explicit boolean calls in legacy callers if needed, or update internal callers `rh_runtime.acquire` / `__main__.py` to pass `strict_interpolation`). Better yet (builder call settled explicitly here): replace the runtime policy flag cleanly with `strict_interpolation: bool = False` across `fetch`, `source_identity`, and `acquire`. On the CLI (`fetch-robinhood`, `poll-robinhood`, `swing`), add `--strict-interpolation` (default `False`) and keep `--accept-unknown` as a harmless deprecated no-op flag so old shell commands do not error.
2. **Three-way per-bar classification in `robinhood.py`**:
   - `item.get("interpolated") is True`: increment `local["interpolated"]`, record open in `interpolated_opens`, **reject**.
   - `"interpolated" in item and item["interpolated"] is not False` (e.g., `None`, string, int): increment `local["invalid"]`, **reject** in all modes.
   - `"interpolated" not in item`: increment `local["interpolation_omitted"]` (and record in `interpolation_omitted_opens`).
     - When `strict_interpolation=True`: **reject**; `source` carries `:strict_interpolation`.
     - When `strict_interpolation=False` (default): **accept**; bar provenance sets `"interpolation": "omitted"` and `"quality": "INTERPOLATION_OMITTED"`; increment `local["emitted"]` and `local["omitted_emitted"]`. `source` remains canonical `robinhood:<interval>:<bounds>:<adjustment_type>`.
   - `item.get("interpolated") is False`: increment `local["not_interpolated"]`, provenance `"interpolation": "explicit_false"`, `"quality": "INTERPOLATION_EXPLICIT_FALSE"`.
3. **Downstream quality & readiness**:
   - `rh_runtime.quality_status(quality)`: returns `'ELIGIBLE_OBSERVATIONS'` when `emitted > 0` and no partial-damage counters (`invalid`, `interpolated`, `missing_results`, `no_usable_symbols`, `out_of_range`, `incomplete_derived_buckets`) are nonzero—even when `omitted_emitted > 0`. Provenance still preserves exact `omitted_emitted` counts in SQLite `acquisitions` and `/snapshot` for full auditability.
   - `Journal.snapshot()`: streams with `ELIGIBLE_OBSERVATIONS`, `RECENT` freshness, warm history, and zero quarantined rows achieve `readiness = "READY_FOR_RESEARCH"` and `ready = True`.
   - `TerminalMonitor`: `risk["UNKNOWN"]` stays `0` on normal omitted-marker streams (only lighting up if legacy `:accept_unknown` or explicit `DATA_QUALITY_UNKNOWN` flags are present). Data Quality panel displays concise provenance note `Interp marker: omitted by provider` without degrading readiness.
   - **Derived `15minute` aggregation (`rh_runtime.aggregate_fifteen`)**: 5-minute input bars with `"interpolation": "omitted"` are eligible inputs for 15-minute RTH triples; if any of the 3 constituent 5-minute bars has `"omitted"`, the derived 15-minute bar provenance records `"interpolation": "omitted"` and `"quality": "INTERPOLATION_OMITTED"` (eligible by default, `ELIGIBLE_OBSERVATIONS`). Existing unit tests in `tests/` are updated to assert default acceptance of omitted markers and explicit rejection under `strict_interpolation=True`.
   - `wizard.py`: remove the interactive `允许探索UNKNOWN？` prompt; default directly to standard mode and note `--strict-interpolation` in CLI documentation.

### 5.2 `XNYS` Session-Close Daily Semantics & Calendar-Aware Daily Freshness (`timeframes.py`, `robinhood.py`, `provider_indicators.py`, `rh_runtime.py`, `native_interpretation.py`, `service.py`)

1. **Canonical NYSE close helper (`timeframes.py`)**:
   - `daily_close(session_label: str) -> datetime`: validates `calendar().is_session(session_label)` and returns `calendar().session_close(session_label).to_pydatetime().astimezone(timezone.utc)` (e.g. `16:00 ET` -> `21:00 UTC` in EST / `20:00 UTC` in EDT; `13:00 ET` -> `18:00 UTC` / `17:00 UTC` on early-close sessions).
   - `daily_session(closed: datetime) -> str`:
     - Accepts canonical `XNYS` session close timestamps (`closed == daily_close(ny_date)` where `ny_date = closed.astimezone(America/New_York).date().isoformat()`) and returns `ny_date`.
     - Also accepts legacy next-UTC-midnight timestamps (`00:00:00Z` where `(closed.date() - 1 day)` is an XNYS session) so existing offline JSONL/CSV replay datasets and unit fixtures continue to load without breaking.
   - `consecutive_daily(old: datetime, new: datetime) -> bool`: continues to compare `calendar().next_session(daily_session(old))` against `daily_session(new)`, plus requires `new > old`.
2. **Robinhood daily normalization (`robinhood.py` & `provider_indicators.py`)**:
   - For `interval == "day"` (`bounds == "regular"`): require `opened` to be midnight UTC (`00:00:00Z`) on a valid `XNYS` session date `label = opened.date().isoformat()`.
   - Compute `closed = daily_close(label)`.
   - If `cutoff < closed`: count `local["incomplete"] += 1` and skip (so during market hours 09:30–15:59 ET, today's unfinished daily bar and unfinished daily indicator point are both excluded).
   - As soon as `cutoff >= closed` (e.g., `16:00:01 ET` on regular days, `13:00:01 ET` on early-close days), both the daily bar and daily native indicators emit with identical `time = closed.isoformat()`.
3. **Calendar-aware daily freshness (`timeframes.is_daily_fresh(closed, now, grace_seconds=7200)`)**:
   - Find the latest `XNYS` session whose `daily_close(session) <= now - timedelta(seconds=grace_seconds)` (using a 2-hour post-close grace window so pulling at 16:05 ET while a provider is still settling today's bar does not prematurely mark yesterday's bar stale, while once today's bar arrives it immediately matches today's session!).
   - More specifically: `bar_session = daily_session(closed)`. If `closed > now + timedelta(seconds=5)`, freshness is `FUTURE`. Otherwise, let `latest_required` be the latest XNYS session whose `session_close + grace_seconds <= now`. If `bar_session >= latest_required`, the daily bar and matching daily native snapshot are `RECENT` (not expired)—so Friday `16:00 ET`'s daily bar stays `RECENT` throughout Saturday, Sunday, and Monday until `18:00 ET` Monday (or immediately updates to Monday's bar as soon as Monday `16:00 ET` is fetched).
   - **`TuiClock.clock_frame` parity (`terminal_monitor.py`)**: `clock_slots` includes a `daily: bool` flag (or `timeframe`) so the 1-second TUI redraw uses `is_daily_fresh(close, now)` for daily streams instead of a numeric `172800s` wall-clock cutoff—preventing `TuiClock` from flipping a weekend `RECENT` daily snapshot to `STALE` on the next tick.
   - `rh_runtime.next_poll_delay` for `interval == "day"` schedules against the next upcoming `XNYS` `session_close + settle_seconds`. `poll_start` for `day` continues to floor `start` to `00:00:00Z` so provider daily `begins_at` (`00:00:00Z`) always falls inside `[start, end)`.

### 5.3 Expanded Native Indicator Packs (`native_runtime.py`, `native_interpretation.py`)

1. **Automatic `context_specs(specs, interval, enabled=True, bounds='regular')`**:
   - Disabled if `not enabled`, `interval == '15minute'`, or `bounds not in ('regular', 'extended')`.
   - **Intraday pack** (`interval in ('minute', '5minute', '10minute', '30minute', 'hour', '4hour')`):
     - `ema` (`{"period": 20}`, `output="last:2"`)
     - `vwap` (`{}`, `output="last:2"`)
     - `atr` (`{"period": 14}`, `output="last:2"`)
     - `rsi` (`{"period": 14}`, `output="last:2"`)
     - `pivot_points` (`{"method": "classic"}`, `output="latest"`)
     *(5 requests per 10-symbol batch; well under the 64-call cap.)*
   - **Daily pack** (`interval == 'day'`, `bounds == 'regular'`):
     - `ema` (`{"period": 20}`, `output="last:2"`)
     - `atr` (`{"period": 14}`, `output="last:2"`)
     - `rsi` (`{"period": 14}`, `output="last:2"`)
     - `macd` (`{"fast_period": 12, "slow_period": 26, "signal_period": 9}`, `output="last:2"`)
     *(4 requests per 10-symbol batch.)*
   - Deduplicate against any user-supplied `--native-indicators` / `--native-config` entries matching the same `(type, interval, effective_parameters)`: if a user requested `latest` while the context pack wants `last:2`, upgrade that spec's `output` in place to `last:2`; if the user requested `last:N` (`N >= 2`) or `series`, keep the user's wider `output` so only one API call and one `slot_key` are produced.
2. **Multi-field & empty-param interpretation (`native_interpretation.py`)**:
   - Handle Robinhood's empty `returned_params: {}` on `vwap` and `pivot_points` without false parameter-mismatch rejection, while strictly checking returned numeric parameters (`period`, `fast_period`, `slow_period`, `signal_period`) when applicable.
   - Validate point alignment (`point == _time(bar['time'])`), receipt causality (`after_bar_seq <= observation_seq`, `receipt <= now`), and freshness (intraday `max(120, 2 * seconds)`, daily `is_daily_fresh`).
   - Populate structured indicator keys on `native_interpretation`:
     - Always present for backward compatibility: `ema20`, `rsi14`.
     - Added per interval pack: `atr14`, plus intraday `vwap`, `pivot_points` (`pivot`, `r1`, `r2`, `r3`, `s1`, `s2`, `s3`), or daily `macd` (`macd`, `signal`, `histogram`, and `histogram_delta` when 2 consecutive closed points exist; if only 1 point exists, `macd` remains `AVAILABLE_SOURCE_UNKNOWN` with `histogram_delta=None`).
     - Partial failure isolation: if one indicator in the pack fails or returns `EMPTY`/`UNDEFINED`, sibling indicators remain `AVAILABLE_SOURCE_UNKNOWN` under overall status `'PARTIAL_NATIVE_CONTEXT'`.
     - Compatibility in `dashboard.html`: update the native summary table renderer in `dashboard.html` so multi-field entries (`pivot_points`, `macd`) and scalar `value` entries both display cleanly without `undefined` text (no canvas level drawing added in P1).
     - When both `close` and `atr14` are valid finite `Decimal`s (`atr14 > 0`), attach `distance` (`close - level`) and `atr_multiple` (`(close - level) / atr14`, rounded to 2 decimal places) on price-denominated overlays (`ema20`, `vwap`, `pivot`).
   - Overall `native_interpretation["status"]`:
     - `'AVAILABLE_SOURCE_UNKNOWN'` when all expected pack indicators for the interval are available;
     - `'PARTIAL_NATIVE_CONTEXT'` when at least one is available;
     - `'UNAVAILABLE'` when zero are available (or `'HISTORICAL_UNAVAILABLE'` when inspecting historical bars).

### 5.4 Unified `StreamSummary` Projection (`pa_lens/context_summary.py`)

Pure function:
```python
summarize_stream(
    bars: Sequence[dict],
    events: Sequence[dict],
    engine_state: dict,
    native_interpretation: dict | None = None,
    *,
    focus_bars: int | None = None,
) -> dict
```

Produces a detached JSON-serializable dictionary:
1. **`regime`**:
   - `context`: `engine_state["context"]` (`trend_up`, `trend_down`, `range_or_transition`, `warmup`)
   - `efficiency_20`: computed from the last up to 20 closes in `bars` (matching `Engine._context()`)
   - `bars_total`: `engine_state.get("total_bars", len(bars))`
   - `bars_in_segment`: `engine_state.get("bars_in_segment", len(bars))`
   - `focus_window_bars`: number of recent bars covered by the active focus window (default `min(len(bars), focus_bars or 30)`)
   - `engine_atr`: `engine_state["local_indicators"]["atr_engine"]["value"]`
2. **`native_summary`**:
   - Normalized, display-ready view of `native_interpretation` (`ema20`, `vwap`, `atr14`, `rsi14`, `pivot_points`, `macd`) with explicit distance/ATR-multiple annotations and availability status.
3. **`active_structures`** (Lifecycle-resolved within the focus window):
   - Retain up to `500` recent events per stream in `Journal` and `Engine.snapshot()` so multi-stage lifecycles across 25–60 focus bars do not lose their root candidate.
   - Group multi-stage events by root episode ID (`root_id = event.get('parent_id') or event['id']`), handling both fan-out from the initial root candidate (used by `mtr_development`, `final_flag_development`, `failed_failure`, `opening_reversal`, `three_push_wedge`, `double_bottom`, `double_top` via `Engine._detector_parents`) and child target updates (`measured_move` `reached` / `invalidated`, whose `parent_id` points to the `confirmed` breakout/DB/DT—updating that setup's `target_state` rather than erasing the confirmed setup). Within each episode group, the chronologically last event defines the episode's current stage and status.
   - Partition into:
     - `live_setups`: currently unresolved actionable `candidate`s and active `confirmed` structures within the focus window whose projections/episodes have not yet been `invalidated` or `expired` (specifically: `double_bottom`, `double_top`, `three_push_wedge`, `range_breakout`, `breakout_observation`, `failed_breakout`, `failed_failure`, `opening_reversal`, `opening_breakout_mode`, `mtr_development`, `final_flag_development`, `tight_channel`, `high_attempt`, `low_attempt`).
     - `recent_resolved`: recently `invalidated` / `reached` / `expired` lifecycle closures within the last 5 bars (for immediate awareness of premise failure or target touch).
   - Each setup item extracts normalized `levels`: `{neckline, confirmation_level, trigger, stop, target, range_high, range_low}` (only keys actually present on that structure, never fabricated), `observed_at`, `direction`, `status`, `family`, and concise Chinese `summary`.
4. **`key_levels`** (Objective price map, sorted descending by price):
   - Collects non-null finite levels from:
     - Latest confirmed 2-left/2-right swing high and swing low from `bars`
     - Previous session high/low (`PDH` / `PDL` when intraday `bars` span prior NY date, or prior daily bar `high` / `low` when `timeframe == 'D'` and `len(bars) >= 2`)
     - Active 20-bar high/low range bounds when `len(bars) >= 20`
     - Active structural `neckline`, `confirmation_level`, `trigger`, `stop`, `target` from `live_setups`
     - Available native price overlays (`EMA20`, `VWAP`, `Pivot P / R1 / S1`)
   - Each entry: `{"kind": ..., "label": ..., "price": float, "distance": float, "atr_multiple": float | None, "source": "structure" | "swing" | "native"}`.
5. **`htf_alignment`**:
   - Explicitly `None` in Phase 1 (reserved contract slot for Phase 2 `--htf` / `--ltf` 4-state verdict).

`Journal.snapshot()` attaches `"summary": summarize_stream(...)` to each stream dictionary alongside existing keys (`bars`, `events`, `display`, `state`, `native_interpretation`).

### 5.5 Presentation Priority & Intraday TUI Upgrade (`presentation.py`, `terminal_monitor.py`)

1. **Actionable structural candidates in `presentation.py`**:
   - Define `_STRUCTURAL_CANDIDATES = {'double_bottom', 'double_top', 'three_push_wedge', 'opening_reversal', 'opening_breakout_mode', 'mtr_development', 'final_flag_development'}`.
   - In `priority(event)`: return `3` when `event['family'] in _STRUCTURAL_CANDIDATES and event['status'] == 'candidate'` (and also include `'mtr_development'` and `'final_flag_development'` `'invalidated'`/`'expired'` in priority `3` lifecycle closures so their termination is not silently dropped). Keep `failed_failure` candidate and noisy single-bar/window candidates (`reversal_bar`, `climax`, `ii`, `ioi`, `tight_trading_range`, `barbwire`) at priority `2`, and `_BASIC` at `0`.
   - Result: default `--display-min-priority 3` immediately surfaces developing structural candidates and their closures in TUI `NEW PA` alerts while keeping single-bar noise suppressed and keeping existing `failed_failure` priority tests intact.
2. **Upgraded `TerminalMonitor` (`terminal_monitor.py`)**:
   - **NATIVE INDICATORS panel**: Renders all indicators present in the interval's pack (`EMA20` with close delta & ATR multiple, `VWAP` with relation, `ATR14` & `RSI14` on one compact line, `Pivot P / R1 / S1` for intraday or `MACD / Sig / Hist` for daily). Every rendered indicator row is registered in `clock_slots` `native_rows` so `clock_frame` replaces all numeric native values with `<LABEL>  <STALE/FUTURE> (last pull)` once the snapshot ages past freshness—never leaving stale numbers visible.
   - **PRICE ACTION panel**:
     - Shows `context`, 20-bar efficiency, and reference ATR.
     - On `NEW PA` (or `HISTORY` / `BASELINE`), renders structural price coordinates (`neckline`, `Trig`, `Stop`, `MM`) right beneath the event header, and lists up to 3 active setups instead of truncating everything to `current[-1]` with `(+N)`.
     - Appends a compact `Key Levels` strip (`SwHi`, `SwLo`, `PDH/PDL` or `20-bar Hi/Lo`) from `stream["summary"]["key_levels"]`.
   - Preserves 100% of existing `TuiClock` detached-snapshot thread safety, resize safety (`format_tui`), NY `EST/EDT` formatting, and `STALE` / `QUARANTINE` / `FIXED END` anti-promotion rules.

### 5.6 Daily Swing Scanner CLI & Wizard Integration (`pa_lens/swing.py`, `__main__.py`, `wizard.py`)

1. **New subcommand `python -m pa_lens swing`**:
   - Arguments:
     - `--symbols NVDA QQQ ...` (1–10 tickers, default `['SPY', 'QQQ', 'NVDA']`)
     - `--warmup-days 250` (calendar days lookback for Robinhood daily fetch, yielding ~170 trading sessions so 20-bar windows, EMA20, MACD, and multi-pivot wedges/DB/DT are thoroughly warmed up; validated `60..1825`)
     - `--focus-bars 25` (recent trading days to highlight for active setups, default `25`, validated `5..120`)
     - `--input <path>` (optional offline canonical daily JSONL/CSV file for credential-free local replay/testing; mutually exclusive with live Robinhood flags; partitions multi-symbol input files by `(symbol, timeframe, source)` in chronological order, requires `timeframe == 'D'`, and filters to `--symbols` only when `--symbols` was explicitly passed on the CLI)
     - `--infra-root`, `--codex-binary`, `--timeout`, `--db` (optional SQLite path; defaults to `:memory:` so one-shot Swing scans require zero database file management unless persistence is requested), `--capture-dir`, `--strict-interpolation`, `--no-native-context`, `--output choices=['text', 'jsonl']` (defaults to `text` on TTY, `jsonl` when piped).
   - Execution flow:
     - Opens `:memory:` (or `--db`) `Journal`, fetches `[now - warmup_days, now]` `day` (`regular`, `split`) bars + daily native indicator pack (`EMA20`, `ATR14`, `RSI14`, `MACD`) via `open_robinhood` (or loads `--input` offline bars).
     - Computes `StreamSummary` with `focus_bars=args.focus_bars` per symbol.
     - Renders a structured multi-ticker terminal report per symbol:
       1. Header: ticker, bar count (`warmup` vs `focus`), latest closed `XNYS` session timestamp in NY time (`EST/EDT`), freshness/quality badge.
       2. Regime & Native Context: `trend_up / trend_down / range_or_transition` (20D efficiency), `Close` vs Native `EMA20` (`+/- ATR`), `ATR14`, `RSI14`, `MACD (macd / signal / histogram & delta)`.
       3. Active & Recent Swing Structures (last `focus_bars` sessions): lifecycle-resolved setups (`double_bottom/top`, `three_push_wedge`, `mtr_development`, `final_flag_development`, `range_breakout`, `H1/H2/L1/L2`, `failed_breakout`) with dates and structural status.
       4. Objective Reference Levels: prior day high/low, recent confirmed swing high/low, 20D range high/low, and any active structure's `neckline / confirmation_level / trigger (reference stop-entry) / invalidation stop / MM target`, plus explicit research-only notice (`probability=None`).
2. **Interactive `wizard` integration (`wizard.py`)**:
   - First prompt selects workflow mode:
     - `1` / `monitor` (default): Intraday / live polling TUI (`poll-robinhood`, default `NVDA · 5m · regular · close-aligned or fixed`).
     - `2` / `swing`: One-shot Daily Swing multi-symbol terminal scan (`swing`, default `SPY QQQ NVDA · 250d warmup · 25d focus`).
   - Previews the exact read-only CLI command and asks confirmation before running.

---

## 6. What Is Left to the Builder

- Exact compact line formatting and column truncation thresholds inside `terminal_monitor.py` and `swing.py` so narrow (`80x24`) and wide (`120x36+`) terminals both render cleanly without line-wrap corruption.
- Internal helper decomposition inside `context_summary.py` and `native_interpretation.py`.
- Updating `service.CORE_SHA256` file list (`context_summary.py`), refreshing `knowledge/concepts.json` code-mapping SHA-256 digests if touched files (`robinhood.py`, `structures.py`, etc.) are pinned by `tests/test_knowledge.py`, and updating bilingual docs (`README.md`, `README.zh-CN.md`, `docs/ROBINHOOD.md`, `docs/TERMINAL_MONITOR.md`, `docs/COVERAGE.md`).

---

## 7. Verification Strategy

- Unit tests for three-way `interpolated` handling (`True` rejected, `None`/malformed rejected, omitted accepted by default with `INTERPOLATION_OMITTED` provenance and `ready=True`, omitted rejected under `--strict-interpolation`).
- Unit tests for `XNYS` daily session close (`16:00 ET` regular close, `13:00 ET` Black Friday early close, mid-session `14:30 ET` incomplete exclusion, weekend/3-day-holiday `is_daily_fresh` behavior, legacy `00:00Z` offline replay compatibility).
- Unit tests for expanded intraday & daily native indicator packs, empty `returned_params` on `vwap` / `pivot_points`, `macd` multi-field & delta extraction, and ATR-multiple calculations.
- Unit tests for `context_summary.summarize_stream` lifecycle parent->child resolution, key-level extraction, and prefix determinism.
- Unit tests for `TerminalMonitor` TUI/text rendering of candidates, structural levels, expanded native indicators, and stale clock aging, plus `pa_lens swing` CLI (`--input` offline + mocked Robinhood provider) and `wizard` `monitor`/`swing` branches.
- Full `unittest` suite, `knowledge/kb.py` validation, and optional bounded read-only live smoke check if Robinhood MCP transport is active.
