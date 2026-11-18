# Robinhood market data

The observer uses the official Robinhood MCP tools through the authenticated Codex
app-server transport in a **separately installed** `robinhood-trading-infra` checkout.
Supply that checkout's root (`--infra-root` for CLI use or `open_robinhood(infra_root=...)`
in Python), or make its `src` importable in the running Python process. The public
observer does not contain that checkout, credentials, or captured live responses.
If the configured MCP is not logged in, the observer fails visibly. It does not
initiate login, accept approvals, or use another provider.

## Request and receipt contract

- The only callable tools are `get_equity_historicals` and `get_equity_quotes`.
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

By default, only a literal `interpolated: false` qualifies. Literal true is counted as
`interpolated`. A missing, null, or malformed marker is `interpolation_unknown`,
not a verified real bar. Both retain their observed open timestamps in quality
metadata. True never produces a signal. By explicit exploratory opt-in, an absent
key may be included in an unverified series; null and malformed values are still
excluded. Every such included bar is marked `DATA_QUALITY_UNKNOWN` in its
`bar_provenance`, and the batch and fetch count `unknown_emitted`. Volume does
not establish interpolation status. Regular-session bars must identify their
provider session as `reg`, and all intraday opens must be minute-aligned.
 `not_interpolated` counts explicit false
markers among unique in-range dated rows, not usable bars; invalid or incomplete rows can still be excluded. `emitted` is the count of eligible
closed bars. Check `no_usable_symbols` and `missing_results` alongside these
counts. Missing/unusable bars are evidence gaps, not proof that no trading occurred.

The normalized source is `robinhood:<interval>:<bounds>:<adjustment_type>`;
exploratory sources append `:accept_unknown` and must not share a verified journal. Do
not mix different sources in a single continuous series. Treat raw captures and
journals as local evidence: do not include them in a public commit.

## Daily swing observations and local indicators

Install `python -m pip install -r requirements.txt` for the XNYS trading calendar.
Daily `begins_at` is the session **date label at midnight UTC**, not an actual
trade time. Only XNYS session dates are eligible. The normalized timestamp is
the **following UTC midnight**, a conservative interval-availability boundary,
not the exchange closing auction (including early closes). The provider label
is retained as `session_date`. Before that boundary the day is incomplete.
Normal weekends, holidays and DST changes do not reset PA; a skipped expected
session clears the rolling context without inventing bars. Edge coverage before
the first/after the last row is not inferred.

Daily patterns use completed session bars as their units. Intraday opening
range/reversal and 1m-to-5m aggregation do not apply. Legacy intraday fill
simulation is unsupported on daily bars. Post-hoc paths can span consecutive
sessions but stop at missing data. Daily bars do not measure observed hours.

`local_indicators` are derived from this segment, not Robinhood indicator values:
EMA20 seeds at first close and has a 20-bar warmup; Wilder RSI14 seeds at the
first 14 changes (15 closes), with flat RSI defined as 50. Existing engine ATR
uses the latest up to 15 true ranges, first bar high-low, with tick floor; not
Wilder ATR. These values and editorial presentation priorities are not calibrated
probabilities. All events/snapshots from exploratory sources retain unknown quality.

## Active runtime (v0.5)

`fetch-robinhood` requests an explicit `--start` / `--end` RFC3339 range.
`poll-robinhood` repeats read-only requests; `--once` or `--count N` bounds the run.
Both accept `--symbols SOXL QQQ`, `--interval`, `--bounds`, `--adjustment`,
`--infra-root`, `--codex-binary`, `--timeout`, `--db`, `--accept-unknown`,
and optional `--capture-dir local_data/private-captures` / `--quotes`.
The provider only calls historical/quote reads. Authentication failures terminate
without auto-login, account access, orders, or another data-source fallback.
Legacy Alpaca and TradingView commands are explicitly named compatibility paths.

`15minute` is a runtime-derived period, **not a Robinhood MCP interval**. It asks
for five-minute regular-session bars and only emits complete, contiguous triples,
anchored at 09:30 America/New_York. A missing member, cross-session combination,
partial end bucket or scheduled early-close violation never produces a 15m bar.
Provenance retains all three original closes and `derived_from=5minute`; volume
is summed, open/close use first/last, high/low use the extrema. Unknown source
quality stays unknown. True interpolated inputs cannot form complete buckets.

Default polling is serial, every 30 seconds **after completion**. `--align-close`
waits between requests for the next 09:30 ET-anchored interval grid plus
`--settle-seconds 10`. Daily uses next UTC midnight availability. The first
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
from provider data; provider technical indicators are not requested. Historical
event focus hides current indicator values instead of leaking future state.
Pinned calendar package version and all acquisition/analytics sources participate
in journal identity; migrate to a new DB after semantic code changes.

Derived-quality count units are explicit: `received`, `unknown_emitted`,
`interpolated`, and other source counters count original five-minute inputs;
`emitted` and `derived_unknown_emitted` count produced fifteen-minute bars.
`incomplete_derived_buckets` counts observed partial/invalid groups only, not
entirely absent buckets. It is not a total missing-feed count. When a requested
symbol has no matching existing stream, polling uses bootstrap history for the
request rather than giving that new symbol only an existing stream's overlap.

### Poll-window boundary safety

Implicit polling starts are floored to the requested bar's open-time grid
(15m uses its derived 09:30 ET grid; daily uses UTC midnight). Each stream's
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
