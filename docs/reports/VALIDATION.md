# Validation: version 0.1 research preview

Run date: 2026-11-18. These are engineering and hypothetical-policy results, not a proven trading edge. First-version thresholds were fixed before these runs; no parameter search was conducted. The chronological slices do not become genuinely unseen data merely because they are named evaluation. Nov17 was already examined and is explicitly a known case.

## Verification evidence
- `python -m unittest discover -s tests -v`: 47 tests passed after the independent-review fixes.
- `python -m compileall -q pa_lens`: passed.
- Synthetic replay CLI and explicit bar-open adapter CLI: passed.
- Authenticated HTTP integration, restart/duplicate/revision/config checks and actual dashboard JS in a small DOM harness: passed.
- Full Chromium visual QA: **not completed**. Browser launch failed with `socket() failed: Operation not permitted`, including a permitted elevated retry. Do not describe the UI as visually verified.
- GitHub CI workflow is provided but **has not run remotely**. No public deployment or verified continuously live market feed.

Independent review found and regression tests fixed: a failed confirmed structure could later appear to hit its active MM target; a gap below a pending stop could incorrectly enter later in the same bar; full raw state made the panel impractically long. The first two are methodological bugs, not reasons to tune parameters. All empirical reports were regenerated afterward.

## Historical-data provenance
Alpaca connector with `feed=sip`, one request per exchange-calendar session. Aug17–Nov17 inclusive: 66 RTH sessions, 25,740 minute bars, 390/session. Prior-three-month part through Nov16: 65 sessions, 25,350 bars. Dataset audit found no missing expected RTH minutes, duplicates or OHLC failures; excluded 66 bars starting 16:00 ET and retained them separately. DST handled with America/New_York.

Source timestamp is minute **open**; adapter explicitly adds one minute before any signal can observe the completed bar. The last 15:59 bar's close is not independently verified as official closing-auction price. Historical data may have been revised after publication and is not an as-published live-feed archive.

CSV SHA256: `6a6a8b8374d02ac8b96b2e8ec8c0eab3b915e0cc4f11b1d59c5753fbcdee0434`.

Adjustment: `connector_default_unverified`; the connector did not expose an adjustment parameter. The corporate-action query returned a $0.0929 cash dividend with Sep22 ex-date and no split; this is a query result, not independent proof of exhaustive issuer records. No client-side price adjustments. Current engine resets daily and paper policy closes daily, but ambiguity remains a data-quality disclosure. Raw licensed data is not committed.

## Fixed policy, not “all signals made money”
- One position at a time; long-only, 100% notional, no additional leverage. SOXL itself is a leveraged ETF.
- A confirmed signal becomes armed only after its bar close; a following bar must reach trigger. First pending setup wins; busy-state signals are ignored.
- Trigger/stop/target from the causal event, positive remaining reward required; 20-bar pending expiry.
- Gap entry uses worse open; gap below invalidation cancels before entry. Stops use worse opening price. Unknown stop/target order is stop-first and marked ambiguous.
- Flat by the 16:00 RTH close proxy; this is a research execution assumption, not guaranteed executable close.
- Costs are adverse price friction on **each side**, including assumed spread/slippage, not measured quotes or exact regulatory/commission fees. No market impact, borrowing, liquidity or actual fills.
- Drawdown is close-marked, not intrabar worst drawdown. Position size can create substantial drawdowns; this is a deliberately fixed diagnostic baseline, not a sizing recommendation.

## Results
Net compounded return, same frozen configuration:

| Segment | Sessions / bars | Trades | 0 bps/side | 1 bp/side | 3 bps/side | 5 bps/side | Max close-mark DD at 3 bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development Aug17–Sep30 | 32 / 12,480 | 171 | -2.246% | -5.533% | -11.778% | -17.611% | 17.690% |
| Validation Oct1–Oct23 | 17 / 6,630 | 101 | -5.469% | -7.359% | -11.027% | -14.550% | 20.066% |
| Fixed historical evaluation Oct26–Nov16 | 16 / 6,240 | 89 | +2.080% | +0.279% | -3.228% | -6.612% | 25.548% |
| Nov17 known case | 1 / 390 | 2 | +1.009% | +0.969% | +0.888% | +0.808% | 6.277% |

**Conclusion:** this first rule set is useful as an auditable observation/replay substrate, not an economically validated trading strategy. Historical evaluation's small gross gain disappears under modest cost assumptions; development and validation were negative even before costs. One positive known day does not rescue that result. Do not optimize on the final slice and continue calling it untouched.

Detailed machine-readable aggregates: [soxl_evaluation_summary.json](soxl_evaluation_summary.json). Pattern counts are not independent trade opportunities or calibrated accuracy. This version has no manually adjudicated pattern-label accuracy study, no day-cluster confidence interval study and no full multi-timeframe ablation. Those remain explicit research gaps.

## Independent daily-open baseline
A separately precommitted, 100%-notional daily RTH-open buy / last-bar-close sell policy, at the same 3 bps/side, returned development +2.4605%, validation -17.5889%, historical evaluation -26.0382%, and Nov17 -2.9031%. [Aggregate evidence](benchmark_summary.json). It holds throughout each session and has different exposure/risk from the PA policy; this is not an equal-risk comparison or a claim that historical opening/closing proxies are guaranteed fills. Cash/no-trade baseline is 0% before opportunity cost. The PA policy's relative loss reduction in some falling periods does not establish positive expectancy.

## Nov17 event audit
34 confirmed structure events: 6 double bottoms, 9 double tops and 19 heuristic range breakouts. The fixed long-only one-position policy accepted only two paper entries:

1. Signal available 10:24 ET; theoretical entry in the minute labeled 10:26 close at 49.05; stop in minute labeled 10:32 close at 47.79. Net -2.627% at 3 bps/side.
2. Signal available 11:02 ET; theoretical entry in minute labeled 11:03 close at 47.33; stop43.50 and target50.61. Neither was reached before policy close; exit proxy at 16:00 bar close49.0682. Net +3.610%, holding almost five hours.

These timestamps are **bar-close labels**, not exact actual execution times. The second trade illustrates the risk of calling the output simply a minute-scalping system: a broad structural stop and a distant MM can imply hours of exposure. All failed/cancelled candidates remain in the event tape; no chart was cleaned to show only winners.

## Reproduce with your own authorized data
```bash
python -m unittest discover -s tests -v
python -m pa_lens replay /path/to/soxl_1m_rth.csv --open-time-minutes 1 --out local_data/soxl
python -m pa_lens evaluate /path/to/soxl_1m_rth.csv --open-time-minutes 1 --out local_data/evaluation
```
Canonical JSONL with `time` already meaning bar-close must omit `--open-time-minutes`. Config hash in this run: `5f37619fe3f2`. Run the identical version/config to compare event tapes; changed rules need a new experiment and a new local database.

## Deferred minor review findings
- Trigger/stop levels offset by tick are not rounded to an exchange order-price grid. Research price levels only, not directly submit-ready orders.
- Config constructors accept bool as a Python numeric subtype; normal CLI/default paths do not supply it. Tighten in a later version.
- Database checks config hash, not code-version migration. Use a new DB after code upgrades; source-version guard is deferred.
