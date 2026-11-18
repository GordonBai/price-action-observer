# Chart inspection and separate terminal monitor acceptance

## Replay UI
The Dashboard now uses full-width candle hit targets and PA markers grouped by observable timestamp. Hover, click/tap, focus and keyboard controls expose exact OHLC, period, UTC/New York time, and existing PA explanations. Daily bars show the session date separately from conservative next-UTC-midnight availability. Markers follow visible list filters and historical focus, never earlier pivot anchors.

On the existing SOXL three-month replay in Mac Chrome, an actual tooltip displayed the daily OHLC and a wedge-invalidated event with its original explanation and unknown-quality label. The coordinator matched all OHLC fields to the saved bar. The page remains open. Specific last-bar/double-top pointer checks were not completed because the user was operating Chrome; automated DOM checks cover multi-event markers, date mapping and historical/filter exclusions. A transient blank file tab was resolved by opening a new correctly loaded tab.

## Separate live terminal
`poll-robinhood --output tui` provides Market, Native Indicators, Price Action and Data Quality panels. The Replay Dashboard does not need this monitor and the terminal does not start a dashboard by default. Text and JSONL remain available. Bootstrap history is explicitly separate from new observations; event IDs and prior accepted closes prevent repeated/old history from becoming new signals. Every screen includes risks across all requested symbols, and clipped panels disclose omitted lines.

Two actual SOXL 5-minute read-only polls of the final formatter completed on 2026-11-18 at approximately 22:05 UTC, after the regular session. The latest closed bar remained 21:00 UTC. The second poll correctly showed no newly accepted bar/no new key PA observation, STALE and DATA_QUALITY_UNKNOWN, and native context unavailable due to expiry. A historical observation retained its existing explanation. This is a bounded after-hours integration test, not an in-session or daemon-lifetime claim.

The Mac Terminal GUI was explicitly denied by the computer-use safety boundary; it was not bypassed. The delivered preview renders captured actual pseudo-terminal output and is labeled as such, not a Mac Terminal screenshot. No persistent market monitor or orders were created.

## Verification
Coordinator and independent reviewer each ran the full 304-test suite: 303 passed, one optional Chromium integration test skipped. Knowledge validation (44 concepts/26 sources), rendered index check, compileall and synthetic replay passed. Independent regression checks covered small viewports with a later-symbol quarantine/error that would previously be hidden; global risk counts now remain visible. No Engine/Journal/source-data semantics changed.
