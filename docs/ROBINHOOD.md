# Robinhood market data

The observer uses the official Robinhood MCP tools through the authenticated Codex
app-server transport in a **separately installed** `robinhood-trading-infra` checkout.
Supply that checkout's root (`--infra-root` for CLI use or `open_robinhood(infra_root=...)`
in Python), or make its `src` importable in the running Python process. The public
observer does not contain that checkout, credentials, or captured live responses.
If the configured MCP is not logged in, the observer fails visibly. It does not
initiate login, accept approvals, or use another provider.

## Request and receipt contract

- The only callable tools are `get_equity_historicals`, `get_equity_quotes`, and
  `get_equity_technical_indicators`.
  Quotes are original provider records and never substitute for bars.
- Historical requests carry an explicit RFC3339 start and end, symbol list,
  canonical interval, bounds, and adjustment type. Defaults are `minute`,
  `regular`, and `split`. Intraday intervals are `minute`, `5minute`,
  `10minute`, `30minute`, `hour`, and `4hour`. `day` maps to a daily `D` bar (regular bounds only).
- Bounds can be `regular`, `extended`, `trading`, `24_5`, `24_7`, or
  `hyper_trading`. Adjustment can be `none`, `split`, or (daily only) `all`.
- A batch has at most ten symbols. Historical time spans are capped conservatively
  by calendar duration at 4,999 intervals, leaving room for an inclusive end in
  the provider's 5,000-bar limit even for continuous sessions. A fetch permits at
  most 128 batches. Exact repeats at chunk seams deduplicate; conflicting records
  at the same symbol and open timestamp fail the fetch rather than taking a side.
- Each batch preserves its request, UTC send/receipt times, a SHA-256 hash of the
  discovered descriptor, a SHA-256 hash of the response, missing symbols, and
  processing counts. A synthetic injected transport may omit descriptors; the
  schema hash is then null, not an invented identifier. Each raw historical bar
  carries the symbol and its originating zero-based batch index.

## Engine eligibility

Provider `begins_at` is the bar's **open**, not its close. The engine accepts opens
inside the requested half-open range. For intraday normalization, the full nominal
interval after the open must have elapsed at the earlier of the request's end
and the acquisition's pre-request cutoff. We do not guess a shorter duration for
a final session bucket when the response does not give its actual close; this can
delay or exclude a shortened terminal bar when the requested end is the session close.

Explicit `interpolated: false` qualifies, and a missing key is eligible by
default with `INTERPOLATION_OMITTED` in `bar_provenance`. The request quality
counts those emitted bars as `omitted_emitted`. Explicit `true` is excluded
and counted as `interpolated`; null and malformed markers are excluded and
counted as `invalid`. `--strict-interpolation` also excludes omitted markers.
Positive volume alone provides no interpolation evidence. Regular-session bars
must identify their provider session as `reg`. Intraday opens must be
minute-aligned. `not_interpolated` counts explicit false markers among
unique in-range rows. `emitted` counts eligible closed bars. Inspect
`no_usable_symbols` and `missing_results` for coverage gaps.

The normalized source is `robinhood:<interval>:<bounds>:<adjustment_type>`.
Strict sources append `:strict_interpolation`. Each symbol, timeframe and
source is a separate series. Keep private captures and journals out of commits.

## Daily swing observations and local indicators

Install `python -m pip install -r requirements.txt` for the XNYS trading calendar.
Daily `begins_at` supplies the session date at midnight UTC. The provider
label is retained as `session_date`. The normalized close is the actual XNYS
session close, normally 16:00 ET or 13:00 ET on scheduled early closes. The
session is incomplete until that boundary. Freshness follows expected XNYS
sessions with a two-hour post-close grace period, so Friday can stay recent
all weekend. Canonical offline input also accepts the legacy next-UTC-midnight
timestamps. Missing an expected session clears rolling context. Weekends,
holidays and DST changes preserve continuity.

```sh
python -m pa_lens swing --symbols SPY QQQ NVDA --warmup-days 250 --focus-bars 25
python -m pa_lens swing --input sessions.csv --symbols NVDA --output jsonl
```

The live scan accepts 1–10 tickers, a warmup of 60–1825 calendar days and a
focus of 5–120 trading bars. It uses regular daily bars with split adjustment
by default. The full input history warms the engine, and the focus controls
which recent structures are highlighted. Offline JSONL/CSV uses the canonical
bar fields and requires `timeframe=D`. It sorts by close within each
`(symbol, timeframe, source)` stream and scans all input symbols unless a
filter is supplied. `--input` excludes live options such as `--warmup-days`,
`--adjustment`, `--strict-interpolation` and `--infra-root`. The default
`:memory:` journal can be overridden with `--db`. Use a separate journal
when scanning an older offline cutoff for an existing stream. Output defaults
to text on a TTY and one JSONL record per stream when piped. Structural
coordinates are research references with `probability=None`.

Daily patterns use completed session bars as their units. Intraday opening
range/reversal and 1m-to-5m aggregation do not apply. Legacy intraday fill
simulation is unsupported on daily bars. Post-hoc paths can span consecutive
sessions but stop at missing data. Daily bars do not measure observed hours.

`local_indicators` are derived from this segment, not Robinhood indicator values:
EMA20 seeds at first close and has a 20-bar warmup; Wilder RSI14 seeds at the
first 14 changes (15 closes), with flat RSI defined as 50. Existing engine ATR
uses the latest up to 15 true ranges, first bar high-low, with tick floor; not
Wilder ATR. These values and editorial presentation priorities are not calibrated
probabilities.

## Active runtime (v0.5)

`fetch-robinhood` requests an explicit `--start` / `--end` RFC3339 range.
`poll-robinhood` repeats read-only requests; `--once` or `--count N` bounds the run.
Both accept `--symbols SOXL QQQ`, `--interval`, `--bounds`, `--adjustment`,
`--infra-root`, `--codex-binary`, `--timeout`, `--db`, `--strict-interpolation`,
and optional `--capture-dir local_data/private-captures` / `--quotes`.
`--accept-unknown` is a deprecated compatibility no-op. The provider uses historical, quote and indicator reads.
Authentication failures terminate the request.
Legacy Alpaca and TradingView commands are explicitly named compatibility paths.

`15minute` is a runtime-derived period, **not a Robinhood MCP interval**. It asks
for five-minute regular-session bars and only emits complete, contiguous triples,
anchored at 09:30 America/New_York. A missing member, cross-session combination,
partial end bucket or scheduled early-close violation never produces a 15m bar.
Provenance retains all three original closes and `derived_from=5minute`; volume
is summed, open/close use first/last, high/low use the extrema. Omitted markers
remain visible in derived-bar provenance. Each input must pass the configured
interpolation policy.

Default polling is serial, every 30 seconds **after completion**. `--align-close`
waits between requests for the next 09:30 ET-anchored interval grid plus
`--settle-seconds 10`. Daily follows the XNYS session close. The first
request is immediate. This is not exchange push streaming, guaranteed publication
latency or a market-hours daemon. Intraday default overlap is 120 minutes; daily
bootstrap is 180 calendar days and subsequent overlap is seven days. The start
expands to the oldest existing requested stream's last close minus overlap after
an outage, subject to provider batch limits. Explicit `--start` overrides this
policy and re-requests that fixed window. No overlap proves older revisions absent.

The journal stores each acquisition's request, schema/response hash, quality
counts and bar provenance. Detailed records are retained and grow with polling;
plan private disk monitoring/rotation, and use bounded runs for validation. The
HTTP snapshot shows at most ten recent acquisitions, twenty provenance entries
and ten batches per acquisition; truncation is explicit, full SQLite evidence
is not deleted. Status is sticky: unknown/partial/no-usable requests keep research
readiness false until separately reviewed in a new journal. Revision and unknown
flags coexist. Partial-status events still describe only accepted original bars,
not a reconstructed complete feed. Provider errors/not_found/restricted results
fail the whole fetch, rather than treating missing results as a successful empty
feed. Raw quote evidence is separate and never patches OHLCV.

Local EMA20, Wilder RSI14 and engine mean-TR volatility are displayed separately
from provider data; native technical indicators are optional independent snapshots. Historical
event focus hides current indicator values instead of leaking future state.
Pinned calendar package version and all acquisition/analytics sources participate
in journal identity; migrate to a new DB after semantic code changes.

Derived-quality count units are explicit: `received`, `omitted_emitted`,
`interpolated`, and other source counters count original five-minute inputs;
`emitted` and `derived_omitted_emitted` count produced fifteen-minute bars.
`omitted_emitted_by_symbol` counts emitted bars per symbol with omission
provenance, in the requested output timeframe.
`incomplete_derived_buckets` counts observed partial/invalid groups only, not
entirely absent buckets. It is not a total missing-feed count. When a requested
symbol has no matching existing stream, polling uses bootstrap history for the
request rather than giving that new symbol only an existing stream's overlap.

### Poll-window boundary safety

Implicit polling starts are floored to the requested bar's open-time grid
(15m uses its derived 09:30 ET grid; daily uses the XNYS session close). Each stream's
first requested lower boundary is retained through acquisition evidence and
restarts. Later overlap/catch-up never expands before that bootstrap boundary,
even when a provider's newest bar is delayed. Requested symbols with different
coverage histories use separate grouped ranges; adding a symbol does not widen
an existing stream's earliest history. Genuine late bars **within** the initial
coverage remain quarantined, including holes before the first accepted bar.
An explicit older `--start` intentionally changes coverage and is best replayed
in a new research database; original-tape journals do not retroactively insert
older history. This prevents scheduler-induced false late-arrival alerts without
silently dropping real provider corrections or late holes.

## Native technical indicators

The observer also permits the read-only `get_equity_technical_indicators` tool.
It is a separate provider snapshot, not a replacement for bars or local EMA/RSI.
Use one type per call, with up to ten symbols per batch. Larger symbol lists are
split without changing the request window. Time windows are never split and
stitched: the server calculation and warmup can change if the start changes.
The provider enforces its bar budget including warmup. If a window is rejected,
try a shorter window or a coarser native interval, not automatic time splitting.

| Types | Optional parameters (provider defaults) | Output fields |
| --- | --- | --- |
| EMA, SMA (`ema`, `sma`) | `period=9` | `value` |
| `rsi`, `roc`, `cci`, `atr`, `mfi` | `period=14` | `value` |
| `williams_r`, `adx` | `period=10` | `value` |
| `momentum` | `period=12` | `value` |
| `donchian_channels` | `period=20` | `lower`, `middle`, `upper` |
| `bollinger_bands` | `period=20`, `num_std=2` | `lower`, `middle`, `upper` |
| `keltner_channels` | `period=20`, `multiplier=2` | `lower`, `middle`, `upper` |
| `macd` | `fast_period=12`, `slow_period=26`, `signal_period=9` | `macd`, `signal`, `histogram` |
| `supertrend` | `period=10`, `multiplier=3` | `value`, `direction` |
| `vwap`, `obv` | none | `value` |
| `pivot_points` | `method=classic` (only method) | `pivot`, `r1`–`r3`, `s1`–`s3` |

Native intervals are `15second`, `30second`, `minute`, `5minute`, `10minute`,
`30minute`, `hour`, `4hour`, `day`, `week`, `month`, `3month`, `6month`,
`year`, `5year`, `10year`, `20year`, and `50year`. There is no native
`15minute` interval. Bounds are `regular` or `extended`; adjustment is
`none`, `split`, or `all` (day or coarser only). `series`, `latest` and
`last:N` affect server output length, not calculation length. Date starts
mean UTC midnight; a date end includes its entire UTC day. A missing end can
be resolved once at the pre-acquisition cutoff.

Normalized points end no later than the earlier of the query end and the
pre-acquisition time. Intraday times use the nominal elapsed interval from
`begins_at`; regular daily points use the actual XNYS session close. Extended daily and week-or-longer results are
raw-only rather than given guessed closes. `latest` in the normalized response
is the final eligible point from the returned window, and can be absent if the
server only returned a newer, ineligible row. Values in the normalized response
are decimal strings or null; null never means zero. Signed fields, including
Supertrend direction, remain signed. Missing fields are separately identified.

Each series holds the **returned** parameters as reported, not inferred
defaults, and points to the batch with the exact request, receipt and evidence
hashes. Its ID includes the exact request and receipt identity; it does not join
snapshots across different windows or receipt times. Warmup status and source
quality are unknown even when values are non-null. The snapshot may incorporate
later provider revisions and does not establish what was known in real time on
a historical date. Provider indicator reports must stay separate from local
indicator calculations and signals.

## Native indicator runtime (v0.6)

Supported intraday intervals automatically request EMA20, VWAP, ATR14, RSI14
and classic pivots. Regular daily mode requests EMA20, ATR14, RSI14 and MACD
(12, 26, 9). The automatic packs request `last:2`; use `--no-native-context`
to skip them. Add `--native-indicators all` for all eighteen types, or a
comma-separated list such as `--native-indicators ema,rsi,macd,pivot_points`.
`--native-output latest` (default), `last:3`, or `series` controls provider output.
`--native-interval` explicitly selects the provider timeframe, otherwise the PA
period is used. **PA 15minute requires an explicit native interval override**:
there is no native 15minute and 5minute values are never relabelled.

`--native-config config.json` adds parameterized requests, including several
instances of the same type. Example contents:

```json
[
  {"type":"ema","parameters":{"period":20}},
  {"type":"ema","parameters":{"period":50}},
  {"type":"macd","parameters":{"fast_period":12,"slow_period":26,"signal_period":9},"output":"last:3"},
  {"type":"supertrend","parameters":{"period":10,"multiplier":3},"interval":"5minute"}
]
```

Only type/parameters/interval/output keys are allowed. Requests are validated
before transport opens and capped at 64 calls including symbol batching.
Use `--native-window-start RFC3339` for a stable warmup input window. Otherwise
a consistent matching saved native window is restored across restarts; if absent,
the original bar coverage start is frozen for the process run. Each polling
iteration freezes its end before serial native calls. Explicit start flags override restored defaults; new configurations may use
the earlier bar coverage window. Always inspect the displayed query window. No
recursive indicator series is split across time windows or stitched. Window
changes receive a distinct query identity, not a historical-revision label.

Each request has AVAILABLE_SOURCE_UNKNOWN, PARTIAL, UNDEFINED, EMPTY, RAW_ONLY
or ERROR status. A failed type does not suppress successful siblings. All-null
latest values remain UNDEFINED, never zero or proof of sufficient warmup.
Supertrend direction is the original signed value, not an inferred long/short
interpretation. Terminal JSON includes every latest multi-column value, requested
and returned parameters, native interval/window, receipt/cutoff and quality.

SQLite stores independent native snapshots with monotonically ordered IDs and
`after_bar_seq`. Latest display slots distinguish symbol/type/parameters/interval/
bounds/adjustment/output; each full input window has its own query ID and retained
history. A new ERROR snapshot replaces the displayed success for that slot, so
previous values cannot masquerade as the latest successful response. Snapshot
output is bounded to 640 slots and twenty points per slot, with explicit truncation
and full point counts; complete saved evidence remains in SQLite. Disk history
grows and needs private retention planning. Optional capture uses the same private
`--capture-dir`; raw provider responses must not be published.

Dashboard separates local calculations and native values. Focusing any historical
PA event hides all current native values; no later native result is inserted into
Engine events or changes PA rules. Native source interpolation, warmup and seed
remain unknown. `latest` means last returned point, not independently verified
current market data; effective time and actual receipt are shown separately.

If selected saved slots have different input starts, automatic restoration fails
before opening transport and asks for an explicit `--native-window-start`; it
never silently changes a recursive indicator's window. Newly selected types or
symbols inherit the single restored window when one exists (displayed per request).
If refresh fails, native current-value rows are hidden and marked DISCONNECTED;
a recently received response is never used as a substitute for point-time freshness.

## Native-first interpretation contract (v0.7)
Current snapshot interpretation uses provider-native context, exact period/source
semantics and matching latest-bar effective time. Receipt must be no later than
generation and after_bar_seq cannot exceed the observed tape. It never restores
a historical interpretation from later native snapshots. Local EMA pattern families
are labeled audit diagnostics and excluded from primary presentation. Missing/
partial/error/undefined/stale values remain unavailable, without local fallback.
Intraday value age is bounded by max(120s,2×interval). Daily freshness follows
the XNYS calendar. Receipt age is reported independently.
Known quarantined bar revisions/late arrivals block comparison with the uncorrected
first-received close. Unknown input/source quality remains visible. Automatic
Context requests are merged by interval and effective parameters. The all-18
selection includes EMA20. EMA9 is available as a separate parameter choice.
