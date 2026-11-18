# Revision-aware ingestion follow-up

Independent review of the initial v0.4 candidate reproduced three operational limitations: changed historical bars stopped polling, older corrections fell outside the single-bar overlap, and quote freshness did not explain transport/revision quality. A closed minute is not provider-immutable: [Alpaca updated bars](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data) can include late trades. [Alpaca's aggregation FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) also explains that no eligible trades can mean no minute bar. A missing interval is not proof of network disconnection.

## Policy now implemented

- Strict manual/webhook `ingest` still rejects revisions. Provider ingestion uses `ingest_observation`: valid changed OHLCV (including volume-only) or late missing bars are quarantined, not applied to the old tape.
- SQLite `observation_audit` stores the original/incoming normalized bar, source identity, type, first/latest receipt time, fingerprint and repeat count. Matching repeated corrections update the repeat count rather than duplicating content. Transport credentials/response bodies are not stored.
- New bars can continue arriving. The affected stream is persistently `DATA_REVIEW_REQUIRED`, never ready. Subsequent event envelopes state `known_revision_or_late_data` and `first_received_bars_not_recomputed`. Historical objects are not mutated. Each audit records the last persisted bar sequence known at receipt; replay compares monotonic bar sequences rather than wall-clock strings. Same-microsecond or backward-clock receipts cannot retroactively relabel older events.
- No automatically corrected current-state interpretation is claimed. Use a distinct corrected-history database for reconciliation; do not trade from an unreconciled structure.
- REST polling rechecks a bounded trailing lookback (120 minutes by default) plus outstanding catch-up. Corrections older than that window may remain unknown.
- Last transport success/empty/error is stored separately from quote freshness and data quality. Errors retain a fixed safe category, not raw exception text. Empty responses are not labeled disconnection. CLI validation/provider errors are reported and retried rather than immediately closing the receiver.
- Dashboard shows readiness prominently and current data-quality/transport details. Historical focus keeps the event's contemporaneous context, not today's revision metadata.

## Verification scope

Synthetic regression tests cover changed close, volume-only correction, late filling of an old missing minute, repeated correction, continued later ingestion, old-window overlap, persistent health, restart event-time identity, transport error versus empty, and no credential leakage. These are deterministic failure simulations, not proof of autonomous recovery under a real provider outage. Original provider sample evidence is versioned separately in [live validation](LIVE_CONNECTOR_VALIDATION.md).

The audit table grows on disk as distinct revisions accumulate; no automatic deletion/retention policy is installed. Readiness remains degraded until explicit separate corrected-history review, not cleared merely because a new quote arrives. No raw market data or source transcript is included in this report.

Runtime identity now includes `service.py` and `feed.py` as well as detector sources: ingestion and receipt-time quality semantics are part of reproducibility, not merely implementation plumbing. Prior journals intentionally fail the identity check and require a new database; no automatic migration clears their history or audit evidence.
