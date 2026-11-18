# Completed-bar live adapter: implementation, not verified deployment

Current environment: `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` are absent. No live Alpaca request was made by this adapter; transport, pagination, time conversion and persistence were tested with deterministic fixtures. Historical SIP access through a separate connector does not establish current SIP subscription rights.

## Alpaca REST polling
Configure your existing Alpaca market-data credentials securely in environment variables `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`, without committing them or putting them in URLs. For a local panel also configure your own random `PA_LENS_TOKEN` (at least16 characters).

```bash
python -m pa_lens poll-alpaca --symbol SOXL --feed sip --once
python -m pa_lens poll-alpaca --symbol SOXL --feed sip --poll-seconds 15 --serve-port 8080
```
The second command keeps the poller and panel on the SAME Journal in the SAME process. Do not run a separate writer and separate `serve` against the same DB: in-memory caches are not a cross-process replication protocol. The new version defaults to `local_data/alpaca-v02.sqlite3`; legacy databases without a source identity are rejected rather than silently migrated.

`--feed iex` is an explicit alternative with different coverage. There is no automatic fallback from SIP to IEX or delayed feed. Requests go only to `https://data.alpaca.markets/v2/stocks/bars`, request 1Min, raw adjustment, ascending sort and paginate explicitly. Secret headers and provider error bodies are not printed. Subscription/rate-limit HTTP codes are reported. No account/trade endpoint exists.

Every provider timestamp is a minute OPEN; the adapter adds one minute and waits another3 seconds before accepting it as complete. Polling interval adds latency; it is not a tick stream. RTH-only filter is09:30 inclusive to16:00 exclusive by New York bar-open clock, weekdays. This is not a standalone holiday/early-close calendar validator. Only actual returned bars are inserted, no fabricated gaps. A restart catches up from the last journaled minute; duplicate bars are idempotent. Historical corrections reject instead of changing old signals.

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

## Research pause
At the user's latest direction, further pattern work is paused pending broader source review. Locally developed H/L attempts and three-push candidates are experimental checkpoints, not proof of complete Brooks knowledge. Infrastructure progress does not remove that evidence boundary.
