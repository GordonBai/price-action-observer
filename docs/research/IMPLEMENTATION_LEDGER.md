# Implementation ledger
Plan: docs/superpowers/plans/2026-11-18-causal-pa.md
Baseline: upstream has zero tests (unittest returns NO TESTS RAN); not a passing test suite.
Ruling: use fresh dedicated clone on feature/causal-price-action, no additional worktree needed or created; upstream main untouched.
Ruling: first version is closed-bar research engine; partial pattern coverage; no unverified live feed or deployment claims.
Task 1 complete: 13 core tests; causal pivots, DB/DT, range MM, manual AB=CD. RED missing module/functions then GREEN; projection invalidation regression separately RED→GREEN.
Task 2 complete: service commits 96fa9dd / 2c4caad; 13 service tests plus Node DOM execution. No public server left running.
Task 3 complete: 16 replay tests + 5 CLI tests; authentic 25740-bar data replay, fixed split cost scenarios, no tuning.
Task 4 complete: bilingual README, coverage/report/CI workflow; full 47/47 suite, compileall and actual CLI evaluation passed. Remote CI not run.
Final review fixed: dead projections remained active -> invalidation regression RED→GREEN.
Final review fixed: gap-open below stop preceded trigger -> cancellation regression RED→GREEN.
Final review fixed: giant state dump obscured signal table -> DOM rendering regression RED→GREEN.
Final minor deferred: non-grid trigger/stop values (research-only levels, not submit-ready orders).
Final minor deferred: Config bool-as-number accepted (default/CLI path unaffected).
Final minor deferred: config hash lacks code-version DB guard (new DB on upgrade documented).
Ruling: browser visual QA blocked by Chromium socket permissions, including elevated retry; DOM/JS/API tested but no visual-pass claim.
Ruling: no standalone real-time data-provider connection or persistent deployment claimed; authenticated ingress is integration-ready only. TradingView needs a Bearer-capable relay.
Ruling: advanced Brooks families remain unimplemented pending literature examples; source directory is not exhaustive audiovisual review.

## Version 0.2 checkpoint and research pause
Parent authorized a further round before user subsequently paused pattern work. Completed prior to pause: advanced H/L attempt observations and three-push candidates, synthetic tests and engine integration. No MTR or full-course completion claim. Stop all subsequent pattern changes pending source review.
Infrastructure completed: memory event bound500; strict bool config rejection; code/config/version journal identity; max64 streams; optional separate TradingView token ingress; Alpaca REST polling with explicit feed/raw and completed-bar timing, CLI same-process panel. Credentials absent: no live API claim.
Independent infra review: two Journal instances could diverge against one SQLite file; fail-fast single-writer lock required. urllib redirects could forward custom secret headers; local two-server test reproduced this, all redirects now rejected, no real credentials ever involved.
Historic v0.1 evaluation report remains frozen evidence, not a new v0.2 performance run.
Infra final: 238d2dd adds fail-fast OS file lock on actual SQLite inode, releases on constructor failure/close; cross-process tests RED→GREEN. Redirect test RED→GREEN, full87 tests pass. Minor deferred: overlapping panel refresh races; direct library make_server permits short tokens while CLI enforces16. Pattern counterexample recorded in COVERAGE without changing rules after pause.
