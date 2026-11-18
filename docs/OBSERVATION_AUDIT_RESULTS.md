# Observation replay evidence — 2026-11-18

This is a structural observation audit, **not a trading backtest or a validated accuracy claim**. Raw third-party OHLCV, event evidence excerpts and detailed local price-path review are intentionally excluded from the public repository.

## Frozen-run results

| Input scope | Bars | Sessions | Observation events | Prefix comparisons |
|---|---:|---:|---:|---:|
| SOXL 2026-11-17 RTH, 1 minute | 390 | 1 | 1,116 | 6 / 6 matched |
| SOXL 2026-08-17 through 2026-11-17 RTH, 1 minute | 25,740 | 66 | 78,883 | 90 / 90 matched |

An event is a feature observation or lifecycle update, not an independent setup, prediction or trade. Many different features can describe the same bar. The single day emitted 28 distinct feature-family names; the multi-month tape additionally includes session-reset bookkeeping. These counts do not mean all 44 knowledge cards have detectors.

The longer audit selects the first observed trading session of each ISO week, plus November 17 as an explicitly known case: 15 sessions, 5,850 bars, 17,635 emitted events and 105 fixed-time review windows. The 17,740 annotation rows remain blank. The selection is not conditioned on returns or event counts. It is still exploratory research, not an untouched out-of-sample experiment.

- Completed independent human labels: **0**.
- Precision, recall and explanation accuracy: **not measured / null**.
- Prefix comparison proves reproducibility at tested cutoffs, not semantic correctness or complete absence of future leakage.
- Adjustment remains `connector_default_unverified`; the source is RTH-only, not extended-hours coverage.

## Insights supported by the case review

An AI-assisted inspection compared four deliberately selected November 17 cases with their source bars. These are explanatory examples, not a random evaluation sample or human ground truth:

1. **A confirmed double bottom need not forecast an advance.** One morning pattern met the local-pivot and neckline-close conditions, then the following 20-bar endpoint was lower. The correct wording is “the structural condition is now observable,” not “the upward direction is confirmed.”
2. **Confirmation delay is visible and consequential.** A later double bottom had already crossed its neckline one bar before the second low completed right-side confirmation. Reporting the observation later is intentional; moving the event back to the low would introduce look-ahead.
3. **A target can be stale when the pattern is first observable.** A late-session double top's projected level had already been touched. The final engine explicitly marks `target_state_at_creation=already_touched`, explains that it is not a new forecast, and does not track it as a fresh objective.
4. **Ordinary three pushes are not automatically a parabolic wedge.** The event now references general swing structure rather than claiming that the numerical three-push approximation establishes accelerating parabolic geometry.

The microchannel definition now excludes nested compression by requiring directional movement of both bounds and non-opposing closes. It still emits observations as a qualifying run extends. This is a narrower engineering definition, not evidence of better predictive accuracy. A separate presentation layer handles repeated display messages without deleting raw audit events.

## Reproducibility identifiers

Canonical data provenance is retained in local audit summaries. The two final runs used identical source-code and knowledge fingerprints:

- Observer package SHA-256: `4a2749d61eb088c07c5bdf14d78a647e1e1520c5e056cea042add30f08a31ded`
- Knowledge JSON SHA-256: `105e6d62012f578bcb23c605a2993da5878b1f6f737f53cbbf2c6f2362a348ea`

The code digest covers sorted `pa_lens/*.py` names and bytes, separated by null bytes; it is not a Git commit hash. Editing any package file invalidates this frozen-run identifier. See [audit protocol](AUDIT_PROTOCOL.md) for commands and independent review procedure. Raw outputs stay under ignored `local_data/` and require appropriate data rights.


## Display-noise projection (raw tape unchanged)

The final presentation defaults use editorial priority 3 and a 15-minute cooldown per family/status/direction. These are UI decisions, not confidence thresholds or trading filters.

| Scope | Raw events retained | Selected events | Display groups | Mean groups/session | Mean groups/observed hour |
|---|---:|---:|---:|---:|---:|
| November 17 | 1,116 | 97 | 62 | 62.00 | 9.54 |
| Three months | 78,883 | 7,080 | 4,854 | 73.55 | 11.31 |

Observed-time denominators are 6.5 hours and 429 hours, respectively, computed from bar count × timeframe; overnight time is excluded. The projection hides routine feature repetition but preserves the original audit tape. Simultaneous events are grouped by observation timestamp. These reductions are not an accuracy improvement or a count of independent opportunities. First-ten-group examples remain local only.

Verification after this audit extension: 178 tests run, successful with 1 browser-dependent test skipped; the 9 audit tests passed. Browser visual acceptance remains a separate check.
