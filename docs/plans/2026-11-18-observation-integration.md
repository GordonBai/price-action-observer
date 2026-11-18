# Knowledge-grounded observation integration

The user corrected the goal: integrate researched concepts and patterns, replay charts against actual price paths, and inspect whether observations/insights are correct. Do not replace that with a trading strategy or returns backtest. Routine implementation choices are delegated.

Chosen approach: extend the existing deterministic, closed-bar Python engine, preserving replay/live input parity. Use the 44-card knowledge registry as source-grounding, not as evidence that every card is detected. No remote LLM or probabilistic classifier is needed. An opaque model would obscure evidence and a new framework would discard tested timing semantics.

1. Add bounded causal observations for mechanically definable candle/sequences, pressure, EMA/channel/range/breakout context. Label thresholds as project approximations; keep subjective MTR, final-flag, broad-channel variants visibly unimplemented unless justified.
2. Fix H2 episode termination ordering, persist candidate/confirmation/invalidation times; no retrospective relabeling.
3. Ground event explanations in stable concept IDs, counterexamples and source links. Persist both engine code and knowledge versions; reject mismatched database recovery.
4. Make ordinary replay observation-only. Retain old policy experiments solely as optional legacy tools, not accuracy or performance proof.
5. Audit 11/17 SOXL as a known case. Export event-time OHLC evidence plus separately labeled future-path diagnostics. Select calendar-based three-month review samples and blank independent annotations. Do not manufacture precision/recall without a labeled denominator.
6. Run synthetic negatives, prefix consistency, journal restart and full regression suite. Report code coverage separately from concept, media and real-data interpretation coverage.

No order submission, live-feed deployment claim, copyrighted raw transcript redistribution or market-data publication. Public release is separately authorized but deferred until verification/review.
