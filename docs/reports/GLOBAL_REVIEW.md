# Workspace and documentation review · 2026-11-18

## Reviewed scope

This pass reviewed the read-only acquisition allowlist, native/local indicator
separation, unknown/interpolated data handling, daily and derived-period
contracts, journal identity/revision boundaries, terminal clock and wizard,
replay/audit interfaces, dependency setup, documentation links and public-tree
hygiene. This is an engineering review, not proof of exhaustive code correctness,
pattern accuracy, data-provider uptime, or complete discretionary PA coverage.

## Changes

- Reorganized both READMEs around offline setup, guided monitoring, direct CLI,
  Replay Dashboard versus live TUI, authentication prerequisites and limits.
- Corrected the coverage page: daily continuity differs from intraday resets;
  local EMA observations are diagnostics excluded from primary groups, even at
  minimum display priority. Raw events remain the audit source.
- Repaired relocated upstream README relative links and distinguished its
  upstream feature claims from this observer's verified capabilities.
- Ignored the documented `.venv/` dependency environment. Private `local_data/`,
  databases, environment files and raw provider captures remain excluded.
- Fixed a conservative multi-symbol native-status bug: a missing ticker no longer
  marks a separately resolved sibling PARTIAL. The complete batch-quality record
  remains attached; shared invalid/field/range problems still degrade siblings.
  The new regression reproduces both outcomes without a live provider request.

## Validation

The final local suite ran 317 tests: 316 passed, one optional Chromium screenshot
check skipped because that executable was unavailable. Node-based dashboard DOM
checks passed. Compilation, knowledge validation (44 concepts / 26 sources),
knowledge render consistency, synthetic sequential replay and diff checks passed.
A local-link check found no unresolved Markdown file links after the relocation
fix. No new live-data availability or continuous-service claim is inferred from
these checks; prior real PTY and data experiments have their own reports.

## Upgrade and preserved state

`native_runtime.py` participates in journal code identity. New runs must use a
new database; existing databases are not rewritten or automatically migrated.
The wizard proposes a fresh path and refuses to overwrite an existing file.
No user process was stopped and no private captures/databases were deleted.
Launching a direct second writer against an owned journal still fails closed;
its current CLI may show a lock RuntimeError traceback rather than a polished
message. This is a usability limitation, not permission to bypass the lock.

## Remaining limits

Unknown interpolation and native source/warm-up remain explicitly unknown.
The default strict path may therefore produce no observations; exploration is
opt-in and never equivalent to verified quality. Daily availability is
conservative; provider-native 15m is unavailable. Native snapshots collected
later are not point-in-time historical truth. Complex PA approximations lack
comprehensive independent human labels. No TradingView public relay or
unattended service deployment is claimed. No orders, account actions, credentials,
third-party raw data, or private absolute paths belong in the public repository.

An independent read-only reviewer reran the final 317-test suite (316 pass,
one optional skip), knowledge validation/render consistency and diff checks.
The sibling-status fix, preserved batch quality, code-identity/new-journal
requirement and bilingual claims were reviewed with no release blocker found.
