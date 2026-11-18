# Robinhood active-data acceptance (2026-11-18)

Status: bounded integration and native-browser acceptance passed; no unattended deployment or predictive accuracy claim.

## Actual read-only acquisition

The installed Robinhood trading infra's `CodexMarketTransport` used the existing official Codex app-server authentication. Only `get_equity_historicals` and `get_equity_quotes` were called. No account, order, login, credential-export, or trading operation was performed. The owned transport was closed and no residual `codex app-server --stdio` process was found.

| Actual request | Returned bars | Strict usable | Explicit unknown-quality exploration |
|---|---:|---:|---:|
| SOXL, 2026-11-17 RTH, minute | 390 | 0 | 390 |
| SOXL, 2026-08-17 RTH, minute | 390 | 0 | 0 |
| SOXL + QQQ, 2026-08-17 through 11-17, daily | 132 (66 each) | 0 | 132 |
| SOXL quote snapshot | 1 result | separate quote only | never converted into a candle |

Recent minute and daily responses omitted `interpolated`; omission is **unknown**, not false. Positive volume does not establish genuine non-interpolated data. Strict mode correctly emitted no bars. Explicit `accept_unknown` exploration reused the *same captured response*, not a second market request, to isolate policy behavior. All August minute bars explicitly had `interpolated=true`; neither mode allowed them into PA analysis.

Consequently, these results establish working acquisition, normalization and exploratory analysis, **not verified-quality trading signals, complete three-month minute coverage, tick streaming, or licensed SIP equivalence**. Bar counts alone are not evidence of usable historical coverage. Raw market captures remain private and are not redistributed with the code.

## Exploratory causal replay

| Stream | Bars | Raw observation events | Events visibly unknown-quality | Prefix checks |
|---|---:|---:|---:|---:|
| SOXL minute, 11/17 known case | 390 | 1,445 | 1,445 | 6/6 |
| SOXL daily | 66 | 258 | 258 | 6/6 |
| QQQ daily | 66 | 278 | 278 | 6/6 |

The same captured bars were replayed through the daily-enabled engine. Each truncated replay produced exactly the observations known by that prefix. Event count includes repetitive state descriptions and is **not insight count, accuracy, profit, or an independent ground-truth evaluation**. November 17 was previously examined and is not a blind test. The same engine outputs were checked in the integrated journal; displayed groups were 73 for the minute stream, 13 for SOXL daily and 16 for QQQ daily. The retained panel window is smaller than the full audit history.

## Daily semantics and Mac journal

Daily source `begins_at` is a UTC session-date label. The normalized availability timestamp is conservatively the following UTC midnight, not an invented minute candle or a claim of availability at the session open. XNYS calendar validation handles expected sessions, weekends and holidays; missing expected sessions reset the analysis segment. Intraday-only detectors are not run on daily bars. Calendar coverage is not symbol-specific halt detection.

The original database-inode `flock` collided with SQLite WAL on Darwin. An owner-private, inode-keyed persistent sidecar now provides mutual exclusion, including hardlink/symlink aliases; Linux also retains the former inode lock for compatibility. Restart through the same canonical database path. Alias locking prevents concurrent bypass; it does **not** promise crash recovery through a different hardlink path with a different WAL filename.

The daily and lock stage passed 243 tests (242 passed, one intentional skip), with independent focused review. Final integration tests and public commit/CI evidence are recorded separately below when complete.

## Final v0.5 integration evidence

- Full local suite: **264 tests, 263 passed, one optional headless-Chromium test skipped**. No warnings. Independent review reran the suite and closed the reported issues.
- Knowledge validation: 44 concepts / 26 sources; rendered index current. Source code mapping hashes refreshed without adding pattern claims.
- Real native Chrome acceptance passed on all four captured-data streams, including daily labels, unknown-quality warnings, source/indicator separation, historical focus without future indicators, authentication failure/recovery and repeated refresh. See [browser evidence](ROBINHOOD_V05_BROWSER.md). The test tab and localhost test server were closed.
- A separate SOXL 5-minute historical request returned 78 source bars. Complete RTH aggregation yielded **26 fifteen-minute bars**, all 26 OHLCV aggregates matched their three inputs, six prefix checks matched, and all 73 resulting events retained unknown-quality labels. The display produced three priority groups. This validates the chosen aggregation, not subjective pattern correctness.
- A two-day SOXL daily request with `adjustment_type=all` succeeded. The provided Robinhood MCP manual correctly states `all` requires daily-or-longer intervals; the initial reversed local restriction was corrected and tested. Intraday `all` is rejected before calling the provider.

### Actual aligned polling and discovered boundary fix

An initial two-round live test revealed an implementation issue: a fractional-second first request start omitted a boundary bar, while the next overlap window extended backward and misclassified that previously unrequested bar as late data. The journal safely quarantined it, but the resulting degraded state was spurious. That test was **not** accepted as a clean run.

The fix aligns request starts to bar-open grids and persists each symbol's initial requested coverage boundary. Subsequent overlap is clamped to that boundary, including provider publication lag; genuinely late holes inside the requested history still quarantine. New symbols receive separate bootstrap windows instead of extending existing streams backward. Tests cover these cases and restart; coverage reconstruction is explicitly ordered by acquisition ID.

After the fix, a **new** journal was used for two real Robinhood minute polls, aligned to minute-close plus five seconds:

| UTC receipt | New bars | Duplicates | Quarantined |
|---|---:|---:|---:|
| 2026-11-18 16:51:06.333250 | 30 | 0 | 0 |
| 2026-11-18 16:52:05.164936 | 1 | 30 | 0 |

The latest canonical bar closed at 16:52:00 UTC, 5.164936 seconds before receipt. This is one observed latency, **not a latency SLA**. The process exited successfully, no owned transport remained, and restart reproduced the event tape exactly. `ready=false` and `DATA_QUALITY_UNKNOWN` persisted: neither freshness nor a successful connection upgrades missing interpolation metadata.

Final runtime identity: `d2af62d13bc5bc13ff978b1eaf964e791dd219b8e963553d73a98299ed619ae4`.
Knowledge identity: `e045f9841669f447ef7213a76c2fcb46d6f6748c66ef0d8c81ab3212afe0c8aa`.
Engine 0.5.0; exchange-calendars 4.13.2. Product code was unchanged after these checks.

## Remaining limits

No daemon/service installation, sleep/network-reconnect soak, overnight/weekend scheduling soak, vendor rate-limit SLA, exhaustive historical availability, or calibrated pattern precision/recall was established. Aligned polling uses a local close grid; it does not suppress all closed-market calls. `--count` is recommended for bounded validation. One interval runs per process; multiple intervals require separate journals. Acquisition audit records grow on disk, and maintenance/rotation is an operator responsibility. Old SIP/Alpaca reports remain explicitly historical evidence and are not fallback or proof of Robinhood coverage. Raw captures and local databases are excluded from publication.
