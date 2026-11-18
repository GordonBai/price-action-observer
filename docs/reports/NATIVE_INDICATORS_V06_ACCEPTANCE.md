# Native Robinhood indicator acceptance

## Scope and contract

This extension adds the read-only `get_equity_technical_indicators` tool alongside equity history and quotes. It does not add account, order, alert-writing or authentication-management tools. The actual live descriptor and the user's Robinhood MCP manual were read; the schema hash accompanies each request. Raw captures remain private, outside the publication set.

All eighteen supported native types were exercised: EMA, SMA, RSI, momentum, ROC, CCI, Williams %R, ATR, MFI, ADX, Donchian channels, Bollinger bands, MACD, Keltner channels, Supertrend, VWAP, OBV and classic pivot points. Per-type parameter restrictions, optional numeric null-to-default behavior and output modes are handled explicitly. Negative values and nulls are preserved; MACD has three fields, channel/band outputs three, Supertrend two and pivot points seven. A null is never displayed as zero.

## Actual provider-layer test

On 2026-11-18, the new adapter made eighteen actual SOXL regular-session 5-minute indicator requests through the installed official Codex transport:

- Fixed requested window: 14:30:00 UTC through 17:23:09.128069 UTC.
- Output: `last:3`, using native default parameters.
- Receipts: 17:23:11.815024 through 17:23:14.371870 UTC.
- Result: **18/18 requests succeeded, three eligible closed points each**. Every latest point had canonical close time 17:20:00 UTC.
- Returned defaults matched the documented fields; VWAP, OBV and pivot points returned empty parameter objects, preserved as such rather than filled with invented metadata.
- Separate actual Supertrend reads verified regular daily output and signed integer direction on both daily and 5-minute responses. The sign is preserved, not given an unverified trading interpretation.

This is evidence of query and normalization behavior, **not** independent verification of the provider's calculation method, input interpolation, seed/warmup completeness, predictive validity, or historical point-in-time truth. All snapshots retain unknown input quality/warmup status. Query-window changes can change recursive indicator values; results are not split by time and stitched together.

Provider tests covered all18 parameter contracts, signed/null values, timestamps, duplicate conflicts, incomplete points, daily session validation, subminute boundaries, partial not-found results and raw-only periods. The full provider-stage suite passed 273 tests (272 passed, one optional browser test skipped). Final integrated validation is recorded below after it runs.

## Time and source limitations

Normalized intraday points require their full nominal interval to have elapsed before the frozen cutoff. Regular daily points use conservative following-UTC-midnight availability. Extended daily and week-or-longer results are explicitly raw-only until their close semantics are implemented. `15minute` is not a native interval and is not silently replaced by `5minute`, `10minute` or `30minute`.

A later query of an old point is a current snapshot of historical calculations, not proof that this exact value was available at that earlier moment. Native indicators remain separate from local EMA20/RSI14, and neither overrides PA rules or becomes a confidence score.

## Final integrated CLI and journal check

The frozen v0.6 CLI made a second, actual SOXL current-session 5-minute acquisition with all18 native indicators and `last:3`. It exited with code 0 and no stderr:

- 36 closed OHLCV bars ingested, zero quarantined; bar source remained `DATA_QUALITY_UNKNOWN`, `ready=false`.
- All18 native requests produced `AVAILABLE_SOURCE_UNKNOWN`, not verified-quality or sufficiently-warmed-up claims.
- Latest effective close: 2026-11-18 17:30:00 UTC (12:30 EST). Native receipts: 17:31:01.822793 through 17:31:04.434986 UTC.
- All54 normalized points contained 99 numeric fields, each exactly matching its original response value. All33 latest fields matched between captured provider output, terminal summary and authenticated dashboard JSON. This is transport/normalization/display consistency, not independent algorithm validation.
- Local indicators and PA output were not replaced. Requested versus returned parameters and all multiple-output fields remain separately accessible.

Final local suite: **285 tests, 284 passed, one optional headless-Chromium test skipped**. Independent review reran the full suite and closed all reported blocking issues. Knowledge remains 44 cards / 26 sources with updated source-code mappings, not new discretionary-pattern coverage.

Review-driven fixes included conflicting restored calculation-window starts (now explicit error rather than silently changing a seed), complete visibility for a single permitted request budget (640 latest slots; 180-slot regression), error-path journal cleanup, and hiding native cached values after a failed dashboard refresh. Same-slot failures replace the displayed successful value with an explicit error, while other successful indicators remain visible. Full private histories remain in SQLite; more than640 distinct accumulated slots are explicitly truncated in snapshot output.

Runtime identity: `1cd14e7605fa41fa36cfea9ed3e8a91d20335ad8aeb8d8d42c854b640316f7f2`.
Knowledge identity: `4338b12ddcd698359cda515f92b0fc972fba0f1ea47c7ffd863b47aa0cc7bbf3`.
Engine 0.6.0; exchange-calendars 4.13.2.

## Remaining limits

Native indicators are opt-in; all18 does not imply continuous background operation. There is no automatic trading, broker-account access, new authentication setup, or daemon installation. The provider calculation/warmup, source interpolation, historical revisions and prediction quality were not independently certified. Native15minute remains unavailable, and unsupported close semantics remain raw-only. Standard PA early-close/holiday tests remain in the complete suite; this does not establish symbol-specific halt coverage or observed Thanksgiving market behavior.

## Native-browser acceptance and cleanup

Actual Google Chrome on the connected Mac displayed all18 native rows, requested/returned parameters, source/warmup unknown labels, point and receipt timestamps, multi-column outputs, and separate local EMA20 versus native EMA9. Selecting an older event hid the native table; returning and repeated refresh restored all18. Invalid authentication cleared the native values and showed DISCONNECTED; valid authentication recovered. See [native-browser report](NATIVE_INDICATORS_V06_BROWSER.md). Only one stream was present in this v0.6 session, so multi-stream switching was not newly claimed as tested.

The test tab was closed and CUA completion recorded. The temporary localhost server and owned Codex transport were stopped. Reopening the real journal reproduced both the native snapshot collection and PA event tape exactly. The ephemeral test token was cleared. A private Markdown output table was prepared for the user; original values/captures and local journals are not committed to this public repository.
