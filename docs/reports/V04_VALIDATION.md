# v0.4 observation acceptance · 2026-11-18

This release extends a PA observer, not a trading policy. Nine formerly unimplemented concepts now have documented operational subsets; eight remain research-only/unimplemented. The 44-card registry does not imply 44 accurate detectors. See [definitions and exclusions](../STRUCTURES.md).

## Frozen replay

Actual private historical SIP input: SOXL RTH 2026-08-17 through 2026-11-17, 66 observed sessions, 25,740 one-minute bars. Provider timestamps are bar-open and converted to close by adding one minute. Adjustment is connector-default/unverified; there is no verified holiday-calendar, split-adjustment or extended-hours completeness claim. Raw bars and annotations remain ignored, not published.

| Scope | Bars | Raw observations | Default display events / groups | Groups per observed hour | Prefix checks |
|---|---:|---:|---:|---:|---:|
| November 17 known case | 390 | 1,387 | 108 / 71 | 10.92 | 6 passed |
| Three months | 25,740 | 96,056 | 7,983 / 5,561 | 12.96 | 90 passed |

These are counts, not independent insights, forecasts or correct predictions. Default priority/cooldown keeps raw audit events intact. Added lifecycle families increased display frequency relative to v0.3; no accuracy improvement is implied. November 17 was previously inspected and is not a blind test.

The fixed weekly calendar sample plus known case spans 15 sessions, 5,850 bars, 21,558 events and 105 no-event-oriented windows: 21,663 blank annotation rows. Human labels remain zero; precision, recall and insight accuracy remain null. Future price paths are explicitly posthoc diagnostics, never detector inputs. Separate AI review cannot be relabeled human/expert truth or extrapolated to all families. The [independent review](INDEPENDENT_REVIEW_V04.md) freezes 48 bars across four windows: strict inside/outside each matched four positive labels; the wider microgap definition exposed two omissions caused by the implementation's additional body-size filter. No general accuracy claim follows.

Replay package SHA256: `893e46c40854bd35395497b9440dc64ed41a7900875feaec3aa871b5bd421cb0`.
Knowledge SHA256: `eeb2211e91c07f4f0df3056d8843490e7ec9819607bceb97b422a6ba590f1fe8`.
Config hash: `5f37619fe3f2`. Service identity pins detector plus service/feed sources; the replay package hash also includes command/audit modules, so hashes intentionally differ.

See the subsequent [revision-ingestion audit and fixes](REVISION_HARDENING.md): first-observed history is preserved, provider changes are audited and degrade readiness, and polling checks a bounded overlap.

## Data and time review

- Completed 5-minute bars require five contiguous one-minute inputs, aligned to New York RTH. Initial partial buckets, second/microsecond offsets, missing minutes and cross-session composition are rejected/reset. Aggregation is a data product, not a multi-timeframe directional judgment.
- Engine resets on New York date changes or missing intervals. Actual holidays/early closes are not inferred from a nominal weekday/RTH filter.
- Source is part of stream identity: historical SIP, connector IEX and raw REST IEX cannot silently merge. Different feed completeness/price discovery means replay and live results are not directly equivalent.
- Saved connector snapshots use the earlier of current time and conservative pre-request clock, with three-second finality grace. Waiting to import cannot make a captured partial bar final. Same-time revisions are rejected, never silently rewritten.
- New database required on code, config or knowledge change. Runtime restart checks were exercised with real connector snapshots.

## Tests and live/browser evidence

Full local suite: 223 tests, 222 passed and one local Chromium test skipped for environment restrictions. A separate actual Cloud Chrome acceptance exercised the unmodified panel against a synthetic snapshot: OHLC, filters, historical focus, stream switching and disconnected state. It did not connect that browser to the live market collector: [browser evidence](BROWSER_ACCEPTANCE_2026-11-18.md).

After revision handling, monotonic receipt ordering and complete runtime pinning, a new journal ran two actual fresh IEX connector rounds: 65 then 67 closed bars; latest closes 15:35 and 15:37 UTC, ages 62.76 / 18.84 seconds. The first request occurred just after a minute boundary, so conservative grace correctly excluded the newest interval. Restart preserved the complete runtime identity, and the second import inserted two new bars and deduplicated 65. Direct SQLite inspection found 67 contiguous minute closes from 14:31 through 15:37, zero gaps or duplicate rows. Runtime SHA256: `129fad2cef90ddadc60171894e0d45dcff6ffa16dfe35ace8fb3130240a52030`. No actual correction arrived in those batches: revision handling remains synthetic-regression evidence, not demonstrated live correction traffic. Earlier transient MCP errors and earlier-hash tests remain separately documented in [versioned real-feed evidence](LIVE_CONNECTOR_VALIDATION.md). Recent SIP was separately denied by subscription.

**Not completed:** unattended multi-hour/day service, automatic outage recovery validation, full-market SIP entitlement, production hosting/TLS, human expert annotations or general subjective PA recognition. No independent provider credentials were available, created or saved. No collector was left running.

## Reproduce locally

```sh
python -m unittest discover -s tests
python knowledge/kb.py validate
python -m pa_lens.audit YOUR_PRIVATE_SOXL_CSV --open-time-minutes 1 --session 2026-11-17 --out local_data/audit-v04-2026-11-17
python -m pa_lens.audit YOUR_PRIVATE_SOXL_CSV --open-time-minutes 1 --out local_data/audit-v04-three-months
```

Do not publish licensed source data, third-party transcript copies or credentials. See previous [v0.3 results](OBSERVATION_VALIDATION.md) for historical comparisons, not current correctness claims.
