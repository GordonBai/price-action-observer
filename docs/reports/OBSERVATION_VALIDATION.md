# v0.3 observation validation · 2026-11-18

This report supersedes strategy returns as the primary evaluation target. The question is whether closed-bar pattern observations and Chinese explanations are auditable against the chart. It is **not** whether a fabricated strategy makes money.

## Verified engineering checks

- `python -m unittest discover -s tests`: 178 tests run, 177 passed, 1 skipped.
- Skipped: real Chromium panel test, blocked by the execution environment's socket permission. No visual QA claim. A separate Node DOM test runs the actual dashboard script and checks candles, filtering, historical focus, sources, XSS handling and interrupted/out-of-order refreshes.
- `python -m compileall -q pa_lens knowledge`: passed.
- Knowledge validation and generated-index check: passed, 44 cards and 26 sources. All code-mapping file hashes match.
- Synthetic regression cases include H2 crossing its episode reference, nested-doji compression not generating opposite microchannels, wedge lifecycle parent links, and MM targets already reached when the structure is confirmed.

## Actual historical replay

Private local dataset: SOXL SIP one-minute regular-session bars, August 17 through November 17, 2026. 66 sessions × 390 bars = 25,740 bars. Input timestamps are bar-open and are advanced one minute for observation availability. Adjustment parameter remains unverified; the dataset is not a complete extended-hours feed. Raw data and event evidence excerpts are not redistributed.

| Run | Bars | Observation records | Independent prefix checks |
|---|---:|---:|---:|
| November 17 known case | 390 | 1,116 | 6 passed |
| Three-month replay | 25,740 | 78,883 | 90 passed |

Counts include basic candle features, repeated run descriptions and lifecycle records. They are not distinct trade opportunities, independent insights or true positives. The panel defaults to priority 3 key structural changes, a 15-minute family/status/direction cooldown and one combined display group per bar. Raw events are unchanged. November 17 reduces to 97 selected events in 62 groups (9.54 groups per observed hour); the three-month tape to 7,080 selected events in 4,854 groups (11.31/hour, 73.55/session). These are editorial display rates, not accuracy gains. Candidates and raw events remain available.

Fixed selection: first observed session of each ISO week, plus November 17. This yields 15 sessions / 5,850 bars, 17,635 sampled events and 17,740 blank annotation rows including fixed-time windows for missed-pattern review. Selection is not based on profitable price paths. This remains exploratory retrospective inspection, not a pristine out-of-sample study.

Human labels completed: **0**. Precision, recall and insight accuracy: **unknown**, not zero or inferred from subsequent price direction. AI spot checks against source bars are not independent human ground truth.

## What the case review teaches

- Structural double-bottom confirmation does not guarantee subsequent upside. The known day contains both a confirmed bottom followed by a lower 20-bar endpoint and another followed by a higher endpoint. Both must remain visible, not cherry-picked.
- A late double-top MM projection had already been touched before confirmation. The engine now explicitly marks `target_state_at_creation=already_touched` and does not track it as a new predictive target.
- Near-close future-path windows are censored by the session end; they must not be compared as if all have the full requested horizon.
- Generic three-push geometry is not a parabolic acceleration pattern or a complete major-trend-reversal model. Knowledge grounding no longer equates those labels.

See [audit protocol](../AUDIT_PROTOCOL.md) for annotation criteria and [coverage](../COVERAGE.md) for thresholds, limits and unimplemented families. Local audit summaries preserve input, code, configuration and knowledge hashes. Historical policy experiments in `VALIDATION.md` are retained only as old experiments, not as evidence of current pattern accuracy.
