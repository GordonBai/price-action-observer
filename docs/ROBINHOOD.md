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
  `10minute`, `30minute`, `hour`, and `4hour`. `day` can be acquired as raw
  evidence only. No exchange-calendar assumptions convert daily opens to closes.
- Bounds can be `regular`, `extended`, `trading`, `24_5`, `24_7`, or
  `hyper_trading`. Adjustment can be `none`, `split`, or (intraday only) `all`.
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
markers among unique in-range dated rows, not usable bars; invalid, incomplete, or
raw-only daily rows can still be excluded. `emitted` is the count of eligible
intraday bars. Check `no_usable_symbols` and `missing_results` alongside these
counts. Missing/unusable bars are evidence gaps, not proof that no trading occurred.

The normalized source is `robinhood:<interval>:<bounds>:<adjustment_type>`;
exploratory sources append `:accept_unknown` and must not share a verified journal. Do
not mix different sources in a single continuous series. Treat raw captures and
journals as local evidence: do not include them in a public commit.
