# Observation audit, not strategy backtest

The user's goal is to compare price-action observations and explanations with actual bars. No trade policy, hypothetical fills or P&L is part of this audit. Existing optional paper-policy code is separate and cannot serve as the accuracy score for patterns.

## Run

From the repository root, with lawfully accessible local data:

```bash
python -m pa_lens.audit /path/to/soxl_1m_rth.csv \
  --open-time-minutes 1 --session 2026-11-17 \
  --out local_data/audit-2026-11-17
python -m pa_lens.audit /path/to/soxl_1m_rth.csv \
  --open-time-minutes 1 --out local_data/audit-three-months
```

Input `timestamp` is bar **open**, explicitly advanced one minute to availability time. Canonical `time` already means bar close. Source identity and adjustment labels are retained. No automatic sorting, interpolating or mixing of streams. A session filter starts with that session, with cold intraday warmup. This matches the current engine's daily reset, not a continuous overnight/daily EMA.

The output directory must be a child of this repository's ignored `local_data/`. These files contain licensed source OHLCV and must **not** be committed or redistributed without permission.

## Artifacts

- `summary.json`: data/code/knowledge hashes, dates, bar counts, event counts, predetermined sample dates and prefix checks. No automatic precision, recall or explanation accuracy.
- `events.jsonl`: unchanged causal event, observation-time source bar, preceding bars and resolvable anchor bars. Evidence is a compact excerpt, not necessarily the entire pattern window. Use the original input for complete review.
- `annotations.jsonl`: blank labels for every emitted event in sampled sessions and every fixed 60-bar window. Window review is needed to find missed patterns; inspecting emitted events alone can only assess false positives.

11/17 is an **already-known case**, never a blind test. The multi-month inspection sample uses the first observed session in every ISO week plus that known case, not the sessions with favorable moves or most signals. It is still an exploratory sample selected after access to this dataset; it is not pristine out-of-sample research.

## Causal checks

Bars enter the same incremental Engine used by the receiver. The path diagnostics are attached only **after** the event tape is complete, in a separate field. For sampled sessions, independent replays at bars 1, 5, 20, 60, 120 and the session end are compared with full-run event prefixes. Session-reset bookkeeping is excluded from this specific prefix comparison because a fresh per-session instance has no previous session. Reset events remain in the full tape. These checks prove reproducibility at those cutoffs, not exhaustive absence of look-ahead, and do not prove semantic accuracy.

## Post-hoc path diagnostics

For each event, the next N bars (default 20) report endpoint close change, maximum high and minimum low relative to the observed price context. Current bar is excluded. A session boundary, input gap or dataset end censors the window. The diagnostics are **not available at observation time**, are never sent back to the detector, and are neither trade returns nor pattern correctness. A double-bottom candidate can be a faithful structural description even if price falls; a bad structural label does not become correct just because price subsequently rises.

## Human review protocol

1. Freeze code, knowledge and data hashes before review. Record whether the reviewer has seen the case.
2. Review the chart only through `observed_at` first. Verify anchors, close-time availability, prior context, candidate/confirmed distinction, Chinese explanation and uncertainty. Do not see `posthoc_path` while assigning structural labels.
3. Use `review_label`: `supported`, `contradicted`, `ambiguous` or `not_applicable`. Add reviewer and reasons. Keep algorithm conformance separate from agreement with the broader discretionary Brooks concept.
4. For every sampled fixed window, independently enumerate missing applicable concepts and their earliest knowable time in `missed_patterns`. Define an event matching tolerance and deduplication protocol before measuring precision/recall. Repeated lifecycle events are not independent ground-truth patterns.
5. Prefer two independent reviewers and adjudication. Record coverage disagreement, not just a final binary vote.
6. Only then unblind future path and separately assess any explicit, testable forward-looking statement. Context labels without a price forecast cannot be scored as up/down forecasts.

Until these labels exist, `precision`, `recall`, `insight_accuracy` are null and completed human labels are zero. Synthetic tests validate the engineered definitions; they do not validate real-market usefulness or calibrate probabilities. No current review sample establishes performance across other symbols, timeframes, event regimes or extended hours.

## Display-noise projection

The raw event tape is retained unchanged. Audit summaries also run the presentation projector with the service default (`min_priority=3`, `cooldown_minutes=15`). `display_projection` contains configuration, filtering statistics, groups by session, and mean groups per session/hour, not full group contents. The hourly denominator is the sum of observed bar durations; overnight time and missing bars do not inflate coverage. Editorial priority is not confidence. A first-ten-group sample is written only to local `display_examples.jsonl` for inspection, not public redistribution. Changing the display filter does not improve detector accuracy.
