# Interactive launch and independent TUI clock acceptance

## Scope

The structured `wizard` command collects stock tickers, supported candle period,
market bounds, polling schedule, run count, explicit unknown-quality opt-in,
lookback, existing infra location, and a new journal path. It previews the
read-only command and requires confirmation. This is not natural-language parsing.
The portable `Start-Monitor.command` launches the wizard without embedding a
particular user's absolute path.

The TUI renderer uses a detached snapshot. Its one-second redraw does not query
market data, access SQLite, increment polling counts, or change observations.
UTC and New York wall clocks are separate from pull start, acquisition receipt,
snapshot age, and closed-bar time. A retained stale snapshot loses available
native values rather than silently treating a clock tick as fresh data. JSONL
and text output retain their existing polling behavior.

## Verification, 2026-11-18

- Full local suite: 314 tests, 313 passed, one optional browser test skipped.
- `compileall`, `git diff --check`, launcher shell syntax, and synthetic replay passed.
- Actual interactive PTY cancellation (`q`) exited normally without acquisition.
- Actual wizard-driven NVDA, one-minute, extended-hours, explicit UNKNOWN,
  three polling rounds completed normally, 22:31:57–22:33:02 UTC.
- Captured 67 rendered frames across 66 distinct wall-clock seconds. During a
  waiting interval, receipt stayed at 22:32:01 while the displayed clock and
  snapshot age advanced each second. CONNECTING and PULLING phases were also
  visible. The final frame said DONE.
- Actual closed-bar time advanced from 22:32 to 22:33 UTC. Native EMA20/RSI14
  were shown with unknown source/warm-up labels. No new key PA event was invented.
- The private journal contains 121 unique bars, three acquisitions, six native
  snapshots, and zero revision/late-arrival audit entries for this short test.
- The owned PTY command exited with status zero; no owned wizard/poller remained.

## Limits

This is a short after-hours read-only test, not a long-running service guarantee
or an overnight-session coverage claim. Interpolation provenance remained
unknown and was explicitly accepted for exploration. No trading or credentials
were configured. No raw market data or private execution captures are published.
A native Terminal GUI access restriction was respected: the test used a command
PTY, and the user launches the visible Terminal manually. A rendered PTY preview
is not a native Terminal screenshot.

## Independent review

A separate read-only reviewer reran all 314 tests (313 pass, one optional skip),
inspected renderer isolation and shutdown, wizard validation/cancellation, and
independently checked the New York fall DST transition (01:30 EDT then 01:30 EST
at the corresponding distinct UTC instants). No release blocker remained.
The real PTY observations above are the implementation team's capture, not a
second independent market-data run.

## New York display correction

A user noticed the original short pull/receipt strings were unlabeled UTC.
The human TUI and text displays now consistently use full New York dates with
EST/EDT: current clock, pull start, bar acquisition receipt, bar availability,
native effective time, and PA observation time. `Bars received` specifically
means bar-acquisition receipt, not native receipt or exchange trade time.
Stored and JSONL timestamps remain UTC. Daily bars retain their conservative
availability meaning; the displayed evening time is not the exchange close.

A second real NVDA one-minute extended-hours PTY test completed two rounds,
17:39:26–17:39:34 EST. The final bar showed 17:39:00 EST, while pull start and
bar receipt showed 17:39:34 EST. Both rounds ended normally. Tests cover the
DST repeated hour, UTC/NY date differences, and daily availability labeling.
Final correction verification: 316 tests, 315 passed and one optional skip,
rerun independently with the same outcome. The reviewer separately checked
spring-forward and fall-back transitions and the daily availability label.
