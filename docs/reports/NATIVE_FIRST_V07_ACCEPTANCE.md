# Native-first context v0.7 acceptance

## Scope
Current PA indicator interpretation uses matching Robinhood-native EMA20 and RSI14, not local fallback. Price-only structures remain independent. Local EMA-dependent events remain marked audit diagnostics and are excluded from primary display. This does not claim all 18 indicators are used as pattern rules.

## Actual read-only verification
On 2026-11-18 at 19:13:35 UTC, the default `fetch-robinhood` path (without enabling optional native flags) fetched SOXL regular-session 5-minute bars and explicitly requested native EMA20 and RSI14. The fresh v0.7 journal contained 56 closed bars, no quarantine, and both native context entries were available with source/warmup unknown. The effective bar closed at 19:10 UTC. The terminal compared the close with native EMA20, and separately described native RSI14. Requested/returned parameters, full query window, source, receipt time and observation sequence were retained. Reopening the journal retained those native values. This verifies integration, not vendor algorithm accuracy, warmup adequacy or predictive performance.

Raw responses, database, terminal values and user screenshots are private, excluded from the public repository. No orders or long-running monitor were started. The one-shot transport exited.

## Tests and review
Independent review ran 293 tests (292 passed, one optional Chromium test skipped) before the final presentation-only refinement. Causal checks include late receipt/observation sequence, effective-bar mismatch, bounds/adjustment, undefined/raw-only/error states, RSI-only partial context, known-revision blocking, restart consistency, historical focus hiding and disconnect clearing. Final release verification is recorded with the release commit/CI.

## Limits
- Current interpretation is generated on snapshot/read; independent historical interpretation snapshots are not persisted. Historical focus explicitly refuses to reconstruct native context from later data.
- Derived 15-minute PA has no equivalent Robinhood-native 15-minute indicator; no 5-minute/10-minute substitution is made.
- Missing, stale or mismatched native evidence is unavailable; local diagnostics are not substituted.
- Provider input quality and sufficient warmup remain unknown. Known quarantined bar revisions block native comparison against the original bar.
- The earlier hour-long monitoring test exceeded its planned stop because its temporary supervisor disappeared. This release does not claim that supervisor/daemon issue is fixed.

### Final coordinator verification
After the presentation refinement, the coordinator reran 294 tests: 293 passed, one optional Chromium test skipped. Knowledge validation (44 concepts/26 sources), rendered-index check, compileall and the synthetic double-bottom replay passed. Installed Chrome independently rendered the actual SOXL snapshot in headless mode; the primary native EMA20/RSI14 interpretation is visible above the candles, with unknown-quality language. This screenshot is a saved one-shot snapshot, not a continuing live session. No desktop unlock was performed.
