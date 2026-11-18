# Real-browser dashboard acceptance · 2026-11-18

## Scope and evidence

Cloud Chrome rendered the actual, unmodified `pa_lens/dashboard.html` through the official managed Sites preview. Tested HTML SHA-256: `fd6f6f2e9daed2574b663bf4689bac62742d69c0889ca153949b5fdbd5643785`.

This was an **actual visual browser/UI check**, not merely DOM simulation. The isolated fixture used the repository's synthetic double-bottom bars, an in-memory Journal snapshot and a second synthetic stream (`TEST2`). Each stream had 14 bars and 49 raw events. No proprietary market data or credentials were involved. The access-token field held an arbitrary dummy string. The preview served a static snapshot and **did not authenticate requests or connect to a market provider**.

## Observed outcomes

| Check | Actual browser result |
|---|---|
| Initial rendering | Dark dashboard readable; OHLC candle bodies and wicks visibly rendered, 14 candles; synthetic source and STALE explicitly shown. |
| Default grouping | 1 important time group; raw audit events remain available. |
| Raw view | 49 / 49 raw events, separate from grouped count. |
| Family/status filtering | `double_bottom` + `candidate` gave one event at 14:39 UTC; `confirmed` gave one at 14:40 UTC. |
| Historical focus | Clicking 14:39 candidate reduced chart from 14 to 9 bars ending 14:39; notice said later bars/events hidden. Context explicitly used saved event context, not latest snapshot. |
| Return to latest | Restored all 14 bars ending 14:44. |
| Stream switching and refresh | Selected TEST2; refreshed; TEST2 remained selected, STALE and 14 candles shown. |
| Malformed response | Static fixture temporarily changed to invalid JSON; browser visibly showed JSON parse error + DISCONNECTED. Restoring fixture and loading again recovered 14 bars. Managed preview can hot-reload on file changes, so this is not proof of retention of old data on refresh failure. |

Screenshots were captured from actual Chrome, full page:
- `pa-browser-grouped.jpg` (128 KiB): grouped stream view.
- `pa-browser-historical.jpg` (124 KiB): historical focus and evidence boundary.

Screenshots are held as local QA artifacts, not embedded proprietary charts or scraped source material in this repository.

## Explicitly not verified by this check

- Actual HTTP token rejection, live provider delivery, persistent real-time running and true freshness transitions: static fixture cannot establish these.
- Actual browser network response reordering, automatic polling timing, mobile/responsive layout, or multiple browser engines.
- Recognition accuracy, predictive value, or real SOXL chart correctness. This fixture verifies presentation/interaction only.
- Existing Node DOM tests cover deterministic stale-response behavior separately; they are not represented as a live network/browser test.

## Environment note

Ordinary short-lived command-launched servers were unavailable to the browser after their tool invocation ended (connection refused). The supported `sites-preview` managed process successfully provided the UI. No network/security settings were changed or bypassed. Isolated preview directory is outside the product repository; it is not a deployment or live trading service.

After acceptance, the isolated managed preview was stopped with the official preview command; status confirmed stopped. No preview service was left running.

## Addendum: revision quarantine UI (same day)

Re-tested real Cloud Chrome after readiness/data-quality UI update. New HTML SHA-256: `af109987bbce215792740a4b28ea66b38b8ecb621123f754689fa59439a3f2ed`.

Fixture construction: ingest the 14 synthetic double-bottom bars via `Journal.ingest_observation`, submit a valid correction to the first bar (close +0.01, quarantined), then ingest one new bar at 14:45. Serve the resulting snapshot through the same isolated managed preview. No actual market data used.

Observed:
- Current view visibly shows **STALE · DATA_REVIEW_REQUIRED · SYNTHETIC / 1m**, with 15 candles through 14:45.
- Current context shows `known_revision_or_late_data`, `first_received_bars_not_recomputed`, revision/quarantine counts 1, and preserve-original-tape policy. Transport is an empty list because this fixture is not a transport test.
- Selecting the pre-revision 14:40 confirmed event reduces chart to 10 candles ending 14:40. Historical context contains the event's saved range/transition explanation and knowledge version, with no injected later revision metadata. Global current stream status continues warning DATA_REVIEW_REQUIRED; it is not represented as knowledge at the historical event.
- Real-browser screenshots: `pa-browser-revision-current.jpg` and `pa-browser-revision-history.jpg`, retained as local QA artifacts.

No product code was changed by this validation. Managed preview was stopped after capture, with `sites-preview status` confirming stopped. Authentication, live feed and sustained operation remain outside this static-fixture check.
