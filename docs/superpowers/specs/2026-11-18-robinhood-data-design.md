# Robinhood-first active market observation

User-requested migration: make Robinhood MCP the active/default data source, reusing the existing Robinhood trading infra; do not trade or introduce automatic fallback. Architecture choices are delegated to the implementer.

Approaches considered: duplicate OAuth/client logic (rejected: credential risk), passively import saved results only (insufficient active-fetch goal), or adapt the existing official Codex app-server transport behind a restrictive PA read-only provider (selected). The infra source remains external/user-installed; no private repo or credentials are vendored.

Provider requests explicitly carry symbols, interval, range, bounds, adjustment. Latest official schema supports minute, 5minute, 10minute, 30minute, hour, 4hour and daily/other periods, with <=5000 bars per explicit range. Chunk conservatively by calendar duration; retain request/receipt/schema identity and do not fabricate usable history from interpolated data. Read-only quote/history are the only callable tools. Completed bar timestamps derive from provider begins_at plus appropriate duration, never label daily bars as minutes.

Raw provider data, deterministic local EMA/RSI, context/pattern observations, and editorial scores are separate layers. Local indicators have explicit seed/warmup and no calibrated probability claim. Quotes never substitute for OHLCV. Historical revising inputs retain existing audit/quality semantics. Recent source success does not prove old-minute history exists: August probe was all interpolation.

Default commands become Robinhood active fetch/poll with explicit source identity. Legacy Alpaca/TradingView remain opt-in compatibility interfaces, not production/default or silent fallback. New code identity requires new journals. Public repo contains code/original docs/synthetic tests only. No token access, account/order endpoints, subscriptions, security setting changes or automatic trade policy.

Daily swing observations are required, not raw-only. Daily source midnight labels map to conservative next-UTC-midnight availability; XNYS session calendar determines valid labels and missing trading sessions. Daily history persists across weekends/holidays without intraday resets. Intraday-only opening/5-minute context detectors are disabled for daily streams. Exchange-calendar dependency is pinned.

Interpolation is tri-state: explicit true is always excluded; absent/unknown is excluded by default. Explicit `--accept-unknown` permits exploratory observations only, visibly and persistently DATA_QUALITY_UNKNOWN with ready=false. Positive volume is not proof of non-interpolation. No mode silently upgrades data quality.
