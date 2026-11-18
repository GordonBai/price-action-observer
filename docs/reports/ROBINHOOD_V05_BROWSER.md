# Robinhood v0.5 native-browser acceptance

2026-11-18. Actual Google Chrome on the user's Mac, operated through CUA. Localhost-only temporary server supplied by coordinator. Real previously captured Robinhood bars replayed into a journal; not a live price-feed validation. No product files changed, no account/trade operations, no public deployment, no new credentials or permissions.

Dashboard SHA-256: `4d3e074bbab02e7fbafb840dfdc21cb67a67139efed9df50892b9e1ca64fb535`.

## Actual observed passes
- Created an isolated local test tab without replacing the existing GitHub tab.
- Valid local token loaded the panel; token remained masked. QQQ daily stream displayed 66 bars and `RECENT · DATA_QUALITY_UNKNOWN · QQQ / 日线 D`, with unknown-quality and non-provider-indicator warnings.
- Daily label was `日线 D`, not `Dm`; independent local EMA20/RSI14/ATR values, methods and warmup were visible.
- Selected an older daily event. Chart's final displayed timestamp moved to that event, subsequent event rows disappeared, the context switched to the saved event context, and the local indicator section explicitly hid latest values rather than backfilling history.
- Returned to latest snapshot; latest chart range and local indicators returned.
- Switched to SOXL derived 15-minute stream: source explicitly said `15minute-derived-5minute`, count 26, `STALE · DATA_QUALITY_UNKNOWN · SOXL / 15m`. Inspected the rendered candlestick chart visually, with visible OHLC wicks/bodies and the historical range.
- Clicked refresh twice; selected 15-minute stream remained selected with no visible error or reset.
- Replaced token with an invalid test value: visible `令牌无效；数据未读取。` and `DISCONNECTED · 当前展示若有数据则为上次快照`. It did not silently represent old display as a fresh successful response.
- Restored valid token and switched to SOXL minute: 390 accumulated bars, explicitly historical/unknown quality; chart showed the retained 240-bar window rather than falsely claiming full-day display.
- Switched to SOXL daily: 66 bars, daily label and separate local indicators rendered normally.
- Cleared the local token, closed the created test tab, and verified the preexisting GitHub tab restored. Automatic-refresh checkbox was never enabled.
- CUA completion_summary succeeded exactly once: `Verified Robinhood observer browser flows`.

## Supplementary automated checks and limits
`tests.test_panel` DOM fixture test passed. Optional real headless Chromium test skipped because its executable was unavailable; this is not counted as a pass. Native Chrome interaction above supplies actual browser evidence for the specified flows. No console instrumentation, mobile layout test, long-running browser soak, closed-market scheduling, or predictive-accuracy validation was performed. The UI status warning was observed; `ready=false` persistence is covered by coordinator/service integration tests, not inferred from a browser-only boolean that is not printed in the UI.

One native AX menu-item click did not change the selected option. Repeating via the standard keyboard dropdown interaction selected the intended stream, verified before refresh. No application defect established.

No screenshots, raw bar data, token, personal browser inventory, or original market captures are included in this report.
