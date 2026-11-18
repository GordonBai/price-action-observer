# Migrating to Robinhood-first v0.5

1. Install `requirements.txt` in the environment used to run the observer. Keep the separately installed Robinhood infra and its existing authorized Codex connection; no credentials are copied into this repository.
2. Start a **new** journal for v0.5. Persisted code, knowledge, configuration and calendar-version identity rejects incompatible journals instead of silently changing historical interpretations. Archive old databases privately, including their SQLite sidecars; do not treat a copied `.db` during active WAL writes as a backup.
3. Use `fetch-robinhood` for a fixed range or `poll-robinhood` for active requests. See [the CLI contract](ROBINHOOD.md). No connector failure triggers another provider, trading, account lookup, automatic login or approval bypass.
4. Strict mode excludes missing interpolation metadata. For exploration, explicitly choose `--accept-unknown` and a separate database. This is not an instruction to treat unknown data as verified. Every such stream stays `DATA_QUALITY_UNKNOWN` / `ready=false`, including after restart.
5. Keep source, interval, bounds and adjustment distinct. `day` means session bars; `15minute` means documented complete 3 × 5-minute aggregation. Quotes remain separate snapshots. Local indicators are not upstream indicator outputs.
6. For a panel during collection, use the collector's `--serve-port`; one process owns a journal. Multiple timeframes require separate processes and databases. Use the same canonical database path on restart, not alternate hardlink paths.
7. Polling preserves first-received bars and quarantines revisions/late holes. Extending an existing stream backward does not rewrite its tape; use a separate research database for a changed historical scope or corrected replay. The persisted initial polling coverage prevents accidental earlier-window expansion. Gaps are data-quality evidence, not proof of a network outage.

## Legacy compatibility

Saved Alpaca exports, manual canonical files and the explicitly named `poll-alpaca` command remain for compatibility. They are not the primary workflow and are never automatic fallback. Historical reports retain their original source and date; they do not demonstrate Robinhood minute coverage. Upstream Pine remains unchanged as a licensed reference. Legacy experimental TradingView ingress is not a deployed public endpoint; do not put credentials in its URL/body or expose this development HTTP listener to the Internet.

## Operational boundary

This release does not install a launch agent, daemon, cloud host, or network/security setting. Bounded real polling and a local browser session were verified; weeks of uptime, recovery while the laptop sleeps, provider limits and full historical retention were not. Acquisition evidence grows on disk. Keep raw captures, journals and generated audit packets private and excluded from Git. The software is an observation/explanation system, not an order executor or a validated trading strategy.
