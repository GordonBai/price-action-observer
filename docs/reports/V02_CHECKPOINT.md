# Version 0.2 local checkpoint — pattern research paused

Verified 2026-11-18: `python -m unittest discover -s tests -v` — 87 tests pass; `python -m compileall -q pa_lens` passes. Real provider credentials absent; no externally verified live traffic, entitlement, public deployment or remote CI run. Full-browser QA remains blocked as recorded in the earlier report.

Implemented infrastructure: explicit Alpaca completed-minute polling, optional same-process panel, default-off TradingView query-secret ingress, version/config/core+advanced source fingerprint, same-DB single-writer OS lock, bounded engine event history and stream count. Redirects are blocked to prevent secret header forwarding. Secrets are not saved in code or logged.

Advanced attempt/wedge observations were created before the user paused pattern implementation for broader source review. They remain an experimental local checkpoint; one H2 reset-order counterexample is documented in COVERAGE. No further pattern work followed the pause. Existing v0.1 historical results remain frozen, not relabeled as a fresh validation of advanced detectors. Advanced observations do not emit paper-trade triggers.

Independent review's important infrastructure findings (multi-writer cache divergence, redirect credential forwarding) received failing-then-passing regression tests. Deferred minors: overlapping dashboard requests can display an older response; direct library server accepts a short secret while CLI enforces16 characters. Do not expose the development HTTP server directly to Internet traffic.
