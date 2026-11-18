# v0.6 native Robinhood indicator browser acceptance

Actual Google Chrome on the user's Mac, through CUA, 2026-11-18. Temporary authenticated localhost server supplied by coordinator. No product modifications, market requests, account operations, trades, or deployment changes by this reviewer.

Dashboard SHA-256: `ddff66e9f1ade81c5796cfdd94826959ba4c3d4bc38a16d4549de8a6cff1c79d`.

## Observed passes
- Opened a separate temporary tab. Valid test token loaded SOXL 5-minute source with 36 accumulated bars, DATA_QUALITY_UNKNOWN and source labeling.
- The native section explicitly said independent request snapshot, not PA input, and displayed 18 items / 18 configurations. All 18 type labels were observed: EMA, SMA, RSI, momentum, ROC, CCI, Williams R, ATR, MFI, ADX, Donchian, Bollinger, MACD, Keltner, Supertrend, VWAP, OBV and Pivot Points.
- Native rows separately displayed requested interval, AVAILABLE_SOURCE_UNKNOWN, effective point timestamp, computed age, receipt timestamp, unknown source quality and unknown warmup. Effective latest point was 17:30 UTC; receipt time was later, not substituted for point time.
- Local section showed EMA20 with first-close seed and 20-bar warmup, independently from the native EMA row whose returned parameters had period 9. Local RSI/ATR were also clearly labeled local, not copied into native fields.
- Actual MACD row displayed macd/signal/histogram including a negative signal; Pivot Points showed pivot/r1-r3/s1-s3; Supertrend showed value and raw direction, without converting direction into an unsupported bullish/bearish assertion. Requested `{}` and returned parameter objects remained visibly separate.
- Expanded MACD detail to observe query window, bounds, adjustment, output last:3, request parameters and processing counts.
- Visually inspected the rendered native table using screenshot observation. Three columns, text wrapping and distinct row boundaries were readable at desktop size. Screenshot/raw numeric values were not saved into this report or public repository.
- Clicked an earlier 17:20 event: chart range ended at that event, later events disappeared, local latest indicators were hidden, and the entire native table was hidden with an explicit warning that the current provider query was not known at the historical event.
- Returned to latest and refreshed twice: native table returned to 18 items with no visible error and stable selected stream.
- Invalid token produced the authentication failure and DISCONNECTED state. Native rows were cleared, with explicit text that prior snapshot values were hidden until refresh succeeds. Correct token restored the 18-item table; all 18 type labels were observed again.
- Cleared the test token, closed only the created tab, and verified the previously active tab was restored. Automatic refresh stayed disabled.
- CUA completion_summary completed exactly once for this acceptance run: `Verified native indicator browser display`.

## Limits
Only one actual stream was supplied in this journal; dropdown inspection confirmed that sole SOXL 5-minute option. Therefore new-version cross-symbol/period switching was not actually tested in-browser, and is not claimed. The earlier v0.5 multi-stream acceptance is separate evidence. The DOM fixture had passed during precheck, while optional headless Chromium was unavailable and skipped; the actual native Chrome actions above are not a claim that the skipped automation passed.

This is bounded UI acceptance on a real acquisition snapshot, not continuous streaming, mathematical equivalence to provider indicators, historical warmup verification, independent data-quality certification, or trading performance validation. No secret, browser inventory, raw capture, screenshot, or numeric market dataset is included here.
