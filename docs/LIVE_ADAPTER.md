# Completed-bar live adapter: implementation, not verified deployment

Current environment: `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` are absent, so the standalone REST poller has not authenticated externally. On 2026-11-18, separate connector-assisted IEX sampling reached the actual engine/journal across four requests while the market was open. Recent SIP was explicitly refused by the provider subscription. See [measured acceptance report](reports/LIVE_CONNECTOR_VALIDATION.md). Historical SIP access does not establish current SIP rights; IEX is a different coverage source, not a silent SIP substitute.

## Alpaca REST polling
Configure your existing Alpaca market-data credentials securely in environment variables `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`, without committing them or putting them in URLs. For a local panel also configure your own random `PA_LENS_TOKEN` (at least16 characters).

```bash
python -m pa_lens poll-alpaca --symbol SOXL --feed sip --once
python -m pa_lens poll-alpaca --symbol SOXL --feed sip --poll-seconds 15 --serve-port 8080
```
The second command keeps the poller and panel on the SAME Journal in the SAME process. Do not run a separate writer and separate `serve` against the same DB: in-memory caches are not a cross-process replication protocol. The new version defaults to `local_data/alpaca-v02.sqlite3`; legacy databases without a source identity are rejected rather than silently migrated.

`--feed iex` is an explicit alternative with different coverage. There is no automatic fallback from SIP to IEX or delayed feed. Requests go only to `https://data.alpaca.markets/v2/stocks/bars`, request 1Min, raw adjustment, ascending sort and paginate explicitly. Secret headers and provider error bodies are not printed. Subscription/rate-limit HTTP codes are reported. No account/trade endpoint exists.

Every provider timestamp is a minute OPEN; the adapter adds one minute and waits another3 seconds before accepting the interval as closed (not provider-immutable). Polling interval adds latency; it is not a tick stream. RTH-only filter is09:30 inclusive to16:00 exclusive by New York bar-open clock, weekdays. This is not a standalone holiday/early-close calendar validator. Only actual returned bars are inserted, no fabricated gaps. A restart catches up while polling also overlaps a bounded lookback; duplicate bars are idempotent. Feed corrections are quarantined and flagged instead of changing old signals; the strict manual/webhook ingest still rejects revisions.

## TradingView-native ingress
See [INGRESS.md](INGRESS.md). The default `/webhook` needs Bearer authentication. To explicitly enable a separate query-secret path compatible with TradingView alerts, configure a distinct random `PA_LENS_TV_TOKEN`, at least16 characters, then:

```bash
python -m pa_lens serve --db local_data/tradingview-v02.sqlite3 --enable-tradingview
```
The path is `/tradingview?token=YOUR_SEPARATE_SECRET`. This is a compatibility endpoint, not an already deployed HTTPS relay. A user-operated TLS reverse proxy/tunnel on a suitable host must forward it. Disable or redact sensitive query strings at EVERY proxy/access-log/monitoring layer. Do not expose the development HTTP server directly. Optional source-IP restrictions are defense in depth, not authentication replacement.

## Operational acceptance still required
1. Establish legitimate entitlement, authenticated TLS ingress or provider access.
2. Verify fresh real bars, close timestamps, source/feed and observed latency.
3. Verify provider corrections, reconnect, gaps, session closure, stale flags and restart behavior on actual traffic.
4. Confirm stable hosting and access controls; keep raw licensed market data private.

The panel's READY_FOR_RESEARCH is freshness/warmup state, not validation of market-data quality, profitability, or continuous service. No public deployment, order execution or real-time SIP entitlement is asserted.

## Connector-assisted import (not unattended polling)
When the connected tool returns a successful `get_stock_bars` structured result, save that JSON privately and import it with:

```bash
python -m pa_lens.feed local_data/provider-result.json --feed iex --symbol SOXL \
  --captured-at 2026-11-18T14:56:09Z --db local_data/connector-current.sqlite3
```

`--captured-at` is the conservative timezone-aware clock taken **before the provider request**, not the later import time. A partial snapshot must never become a final bar merely because time passes. The bridge waits three seconds after bar close relative to this capture cutoff, validates request feed/symbol/timeframe and chronological rows, and keeps `adjustment_unverified` in the source. Feed mismatch is rejected. It obtains no credentials and schedules no future requests. To keep sampling, an authorized agent must actually invoke the connector again; a saved JSON file cannot become a live provider.

The current bounded observation test is evidence of IEX connectivity and incremental ingestion, not 24/7 service, external UI deployment, live SIP entitlement or continuous monitoring. No subscription was bought, no credentials created, and no network security setting changed.

## Revision-aware observation policy

A closed interval is not an immutable provider-final bar: late eligible trades can change OHLCV. The three-second grace only excludes clearly unfinished intervals. Feed ingestion preserves the first-observed bar and its causal observation tape. A differing same-time bar (including volume-only changes), or a late bar filling an older missing interval, goes into a persistent deduplicated revision audit instead of silently rewriting history or stopping all future collection. Known-affected streams are `DATA_REVIEW_REQUIRED`, not ready; later observations remain explicitly based on the original unreconciled tape. A separately rebuilt corrected-history database is required for corrected analysis; automatic reconciliation is not claimed.

REST polling re-requests a bounded trailing lookback (default 120 minutes) plus any outstanding catch-up. Older-than-window corrections can remain undetected; this is not exhaustive revision discovery. Transport success/error/empty response is separate from bar freshness and revision quality. Missing minute intervals have unknown cause: they may reflect no eligible trades, sparse IEX coverage or transport/provider omissions. No flat or zero-volume bars are fabricated; conservative five-minute aggregates require all five actual minute inputs.
