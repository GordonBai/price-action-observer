# Bounded current-market connector validation · 2026-11-18

## Result

Current SOXL **IEX** bars were retrieved through the authorized Alpaca connector and passed into the actual incremental Engine and SQLite Journal. Four requests spanned provider clocks 09:53:46 through 09:57:17 America/New_York while `is_open=true`. This is a bounded, agent-assisted connectivity/ingestion test, **not** continuous unattended deployment and **not** consolidated SIP coverage.

Recent SIP was explicitly denied with `subscription does not permit querying recent SIP data`. No automatic feed fallback was used: IEX was selected and labeled as a separate test. Standalone REST credentials remain absent. No purchase, credential creation, account action, or security/network configuration change was made.

## Observed import sequence

All timestamps below are UTC. Provider timestamps name bar-open; the canonical stream uses close time. The importer conservatively evaluates finality against the pre-request provider clock, not against a later import time.

| Request clock | Rows returned | Closed rows accepted | New / duplicate | Latest canonical close | Age at import |
|---|---:|---:|---:|---|---:|
| 14:53:46.596 | 23 | 23 | 23 / 0 | 14:53:00 | 168.74 s |
| 14:55:01.276 | 25 | 24 | 1 / 23 | 14:54:00 | 108.76 s |
| 14:56:09.333 | 26 | 26 | 2 / 24 | 14:56:00 | 18.79 s |
| 14:57:17.217 | 27 | 27 | 1 / 26 | 14:57:00 | 18.85 s |

The initial file waited while the bridge was implemented, so its first import was correctly STALE. The last three imports were RECENT. These ages measure close-to-import time, not exchange-to-provider latency. Request two contained a bar whose close was less than three seconds before the query clock; it was excluded rather than promoted to final by waiting until import. Later fresh requests supplied that minute safely.

Final journal: 27 unique minute bars, close times 14:31–14:57, 91 raw observations and five default-priority display groups. Repeated history was idempotent; no duplicate rows or corrections were silently applied. Journal was reopened between the initial catch-up and subsequent requests; the latter two requests were consumed by one bounded running process. The process exited after the fourth request. There is **no still-running collector** from this test.

## Reproducibility and scope

- Source identity: `alpaca-connector:iex:adjustment_unverified`.
- Engine version: `0.3.0`.
- Runtime engine-source hash: `c565da2740c4183798ca4e2d65c36b36fb5260ae7006d297d0d44435309d38f2`.
- Knowledge hash: `105e6d62012f578bcb23c605a2993da5878b1f6f737f53cbbf2c6f2362a348ea`.
- Private raw requests/responses, clocks, snapshots, import reports and database are under ignored `local_data/live-validation/`. Do not redistribute licensed raw quotes.
- Eight new deterministic bridge tests cover provenance, feed mismatch, unfinished snapshot finality, strict ordering/revisions, symbol/timeframe checks and duplicate CLI import. These tests do not establish market-data accuracy.

A preliminary local harness trial accepted snapshots against import time. That trial was rejected, not counted as final validation, and replaced with capture-cutoff validation plus a regression test. The table refers only to the corrected `connector-closed-test.sqlite3` run.

The engine was deliberately pinned for this experiment while other pattern work proceeded. If the integrated engine/knowledge changes, this report remains evidence for the stated runtime only; run a new database for final-version acceptance. It cannot stand in for multi-hour reliability, reconnect/backoff under actual outages, public TLS hosting, entitlement to full-market real-time SIP, or human verification of pattern accuracy.

## Remaining deployment gate

The connector is available to the assistant, not as an exportable credential or a standalone daemon API. A persistently scheduled bridge would need a supported scheduler/runtime capable of invoking it, or user-configured existing REST credentials. Neither was silently created here. The standalone adapter and one-shot import are ready to use, but ongoing availability must be demonstrated by future actual calls and fresh bars, not inferred from a successful bounded test.

## v0.4.0 follow-up: transient connector outage and captured-data regression

At approximately 15:00–15:01 UTC a fresh two-round validation was attempted after the additional pattern integration. The connector returned MCP `-32603 Internal error` on repeated `get_clock` calls and on `get_stock_bars`. No fresh response was obtained during those failed attempts; recovery is recorded separately below. This failure is distinct from the earlier explicit SIP entitlement refusal. The four-round test above remains **v0.3.0 evidence**; subsequent v0.4.0 evidence is separated below.

A new isolated v0.4.0 journal was tested with the already captured fourth response, explicitly as **captured-data regression**, not a new market sample. At 15:01:03 UTC it imported 27 closed bars; a second process reopened it and returned 0 inserts / 27 duplicates. Latest close was still 14:57 UTC and health correctly showed STALE (about 244 seconds), NOT_READY and `live_verified=false`. No old database identity was overridden.

- v0.4.0 runtime engine-source hash: `b2d74a97f880e3dafbffefd12779db0ac25286ddbf0a452d295e2aea1b256c92`.
- Knowledge hash: `b6f9cb740c743a992f9fcae6b458f56c39965117115cf36defa66a4a5e94bbc8`.
- Config hash: `5f37619fe3f2`.
- Private regression artifacts: ignored `local_data/live-final/`.
- `python -m unittest tests.test_connector_feed tests.test_feed -q`: 15 tests passed.

The fresh-data acceptance gate requires at least two successful, newly captured closed-bar responses across minute boundaries into a new journal on the reviewed runtime. The service outage does not justify substituting old data or claiming uninterrupted collection. No collector was left running.

## v0.4.0 recovery: two fresh connector rounds passed

The connector subsequently recovered without credentials or configuration changes. Two newly requested IEX batches were imported into a **different new database**, `local_data/live-final/fresh-validation.sqlite3`, on the v0.4.0 runtime/hash above. Both provider clocks indicated the market was open. These are actual new requests, not the captured-data regression above.

| Pre-request UTC clock | Closed rows accepted | New / duplicate | Latest canonical close | Age at import |
|---|---:|---:|---|---:|
| 15:01:29.820832 | 31 | 31 / 0 | 15:01:00 | 30.60 s |
| 15:02:28.508830 | 32 | 1 / 31 | 15:02:00 | 30.47 s |

The two one-shot processes reopened the same new database across a minute boundary. Source remained `alpaca-connector:iex:adjustment_unverified`; identity remained identical on both imports. Health reported RECENT_INPUT / READY_FOR_RESEARCH, while `live_verified` remained false, intentionally avoiding a blanket real-time guarantee. Private provider outputs, pre-request clocks and reports are `local_data/live-final/{round,clock,report}-{1,2}.json`.

This satisfies a bounded fresh-bar connectivity/restart/idempotence check for this exact v0.4.0 hash. It does **not** establish a daemon, automatic reconnect after the observed MCP errors, multi-hour uptime, external webhook reachability, or SIP access. The agent retried the connector; no autonomous recovery was tested. No collector was left running. Pattern changes after this recorded hash require their own regression assessment.

## Final reviewed runtime: one fresh round; second blocked

After review fixes to minute-grid validation and final-flag knowledge mapping, code and knowledge identities changed. A further **new** journal was created at ignored `local_data/live-reviewed/fresh-validation.sqlite3`; earlier test databases were not migrated or overridden.

- Engine version: `0.4.0`.
- Engine-source hash: `549d9e82f0476df473c3ce2a453c99084a1ed0732904cec58934a56ffac6203a`.
- Knowledge hash: `eeb2211e91c07f4f0df3056d8843490e7ec9819607bceb97b422a6ba590f1fe8`.
- Config hash: `5f37619fe3f2`.
- Provider pre-request clock: `2026-11-18T15:06:15.898124Z`, market open.
- New IEX response: 36 closed bars imported; latest close 15:06 UTC, age at import 17.31 seconds. Health RECENT_INPUT / READY_FOR_RESEARCH, `live_verified=false`.
- Direct SQLite integrity check: 36 unique bars from 14:31 through 15:06 UTC, every adjacent interval exactly 60 seconds, zero gaps and duplicates in that observed span.
- Feed unit checks rerun: 16 passed.

The second fresh round was attempted after the next minute boundary, but three provider-clock calls and two direct bar calls returned MCP `-32603 Internal error`. Direct bar retries used local UTC as a conservative pre-request cutoff, without dependence on the failed provider clock; they also failed. No second fresh response was obtained for this final hash. Thus **two-round validation remains passed only for the preceding hash**, while the final reviewed hash has one actual fresh-data round plus unit/regression evidence. This is a documented incomplete acceptance item, not evidence of continuous reliable operation. No collector was left running. Private raw evidence and integrity summary remain under `local_data/live-reviewed/`, not in public git.

## Transport/revision handling follow-up

After revision quarantine and transport-health changes, an additional pre-pin run at 15:32:16 UTC fetched and imported 62 fresh IEX bars (latest close 15:32, age 17.77 seconds, no quarantines). It is preserved privately under `local_data/live-transport-final/`. At that point the engine identity still excluded adapter/service source: feed SHA256 was `f8aadf893d1559084d69801d7c556f3141e3ad643158a742ae066ea8d5cf2afa`, service SHA256 was `a871e53be3374ee6594f9ac6a8094ea74383a4b7e6685953d27054b845ca40a9`. This was **not** reused as evidence for the subsequent corrected identity-pinning implementation. The next test used another new database after feed/service were included in the runtime hash.

## Latest fully pinned runtime: two fresh rounds passed

A new journal at ignored `local_data/live-pinned/fresh.sqlite3` ran two fresh IEX connector requests after the identity correction. Each request used the local UTC clock captured **before** the request, minus three seconds for its requested end, as the conservative finality cutoff. No failed response or old captured snapshot was substituted.

- Engine version: `0.4.0`; source hash including feed and service: `5e6e75fbdc77ef46e0bccd0105e8857da4eee1bee5dcd8905505182c9bf48cfc`.
- Knowledge hash: `eeb2211e91c07f4f0df3056d8843490e7ec9819607bceb97b422a6ba590f1fe8`.
- Config hash: `5f37619fe3f2`.

| Pre-request UTC | Closed rows | New / duplicate / quarantined | Latest close | Age at import |
|---|---:|---:|---|---:|
| 15:33:18.828 | 63 | 63 / 0 / 0 | 15:33:00 | 20.56 s |
| 15:34:24.804 | 64 | 1 / 63 / 0 | 15:34:00 | 25.48 s |

Both processes reported the same complete runtime identity and RECENT_INPUT / READY_FOR_RESEARCH, with `live_verified=false`. A direct SQLite check found **64 unique closed bars, 14:31–15:34 UTC, all adjacent intervals exactly 60 seconds, zero gaps and zero duplicate rows**. The second process reopened the first process's journal successfully. No revisions happened in these two actual batches, so revision quarantine is established by tests, not by this particular market sample. CLI transport-health list was empty; this test does not validate a polling daemon's transport-health state machine.

Private responses, clocks, reports and integrity summary remain under `local_data/live-pinned/`. This resolves the earlier final-version two-round gap for the exact hash named here, but not the outstanding unattended-collection, automatic reconnect, uptime or SIP-entitlement limitations. The two import processes exited; no collector remains running. Earlier version reports remain chronological evidence, not interchangeable validation.

## Sequence-based audit-boundary runtime: final two-round check

After correcting audit provenance to use the received-bar sequence rather than wall-clock microsecond ordering, another new journal was used at ignored `local_data/live-sequence-final/fresh.sqlite3`. Both requests below are fresh market requests; no prior response was reused.

- Complete runtime source hash: `129fad2cef90ddadc60171894e0d45dcff6ffa16dfe35ace8fb3130240a52030`.
- Knowledge hash: `eeb2211e91c07f4f0df3056d8843490e7ec9819607bceb97b422a6ba590f1fe8`.
- Engine `0.4.0`, config `5f37619fe3f2`.

| Local UTC pre-request cutoff | Closed rows | New / duplicate / quarantined | Latest close | Age at import |
|---|---:|---:|---|---:|
| 15:36:01.162 | 65 | 65 / 0 / 0 | 15:35:00 | 62.76 s |
| 15:37:17.805 | 67 | 2 / 65 / 0 | 15:37:00 | 18.84 s |

The first cutoff was less than three seconds after the minute boundary, so the 15:36 close was not admitted prematurely. A later fresh request supplied it and the next minute. SQLite independently verified **67 unique closed bars from 14:31–15:37 UTC, zero missing minute intervals and zero duplicate rows**. Runtime identities matched across both processes. Both reported RECENT_INPUT / READY_FOR_RESEARCH with `live_verified=false`; no revision or late-arrival quarantine was observed in these batches. Eighteen feed tests passed. Raw responses, conservative clocks, import reports and integrity result remain private and gitignored.

This is the latest exact-runtime bounded connectivity evidence, replacing no historical report. It does not establish continuous deployment, autonomous retry, semantic pattern accuracy or SIP entitlement. No collector was left running; all standalone/deployment limitations above remain.
