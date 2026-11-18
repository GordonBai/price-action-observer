# Robinhood native indicator evidence

User request: connect all 18 native Robinhood technical-indicator types, including their actual parameters and multiple output fields; make configurable values visible in terminal and dashboard, distinct from local PA calculations. Decisions are delegated; this extends the existing read-only observer, not a trading strategy.

Approaches considered: replace local indicators with provider values (rejected because methods/window/warmup differ); compute all 18 locally (does not meet native-data request); add a separate provider-evidence layer through the existing official MCP transport (selected).

Only `get_equity_technical_indicators` is added to the existing history/quote allowlist. Discover the live descriptor and preserve request, response/schema hashes, receipt/cutoff and raw-vs-usable point separation. Every complete query window is its own snapshot identity; do not split time windows and stitch recursive indicators. Symbol batching is permitted. Values can be negative, zero or null, and multi-column outputs must not be flattened. Requested parameters and returned parameter metadata stay distinct.

Intraday points become usable only after the native bar interval has elapsed at the frozen acquisition cutoff. Daily points use the same conservative following-UTC-midnight availability as daily bars. Longer periods whose boundary semantics are not implemented remain explicitly raw-only rather than receiving invented close times. Native 15minute is unsupported; never label 5minute indicator values as 15minute.

Runtime selection supports all 18 or a list of configurable indicator requests. Each type/request yields explicit success, empty, raw-only, or safe error status; one failing request does not conceal successful siblings. Provider inputs' interpolation and warmup remain unknown unless explicit evidence says otherwise. A non-null value is not a proof of sufficient warmup or verified source quality. No native output silently replaces local EMA20/RSI14, alters PA rules, or becomes a calibrated signal score.

Journal stores indicator snapshots separately with their receipt and query identity. Latest dashboard/terminal summaries retain native methods/parameters/window/quality. Focusing an earlier event hides later native snapshots instead of retrospectively attaching their values to the event. Native evidence is never an order request.

Verification: parameter/type contracts for all18, multi-output/null/negative fields, cutoff and daily boundaries, mismatch/error/partial results, persisted snapshots and historical-focus safety; actual read-only SOXL current-session 5minute calls and terminal/UI inspection. Captures remain private. Publish original code/docs/tests only, after independent review and CI. No daemon installation or new credentials.
