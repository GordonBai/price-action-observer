# Robinhood-first Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Active, auditable Robinhood market-data acquisition with local indicators and PA observations.
**Architecture:** Restricted provider wraps existing authenticated CodexMarketTransport. Acquisition/normalization is separate from local analytics and observation engine; journal preserves first-received evidence and audits corrections.
**Tech Stack:** Python + pinned exchange-calendars, external installed robinhood trading infra, SQLite, existing HTML dashboard.
**Spec:** docs/superpowers/specs/2026-11-18-robinhood-data-design.md

## Global Constraints
No orders/credentials/fallback. Preserve provenance/interpolation/finality/quality. New journal on code identity change. Real captures remain private.

## Review Focus
- Old history filled entirely by interpolations must not become signals.
- Time-range chunk overlap must neither duplicate nor drop final bars.
- Daily/session boundaries must not be coerced into minute semantics.
- Auth/outage must fail visibly without exposing errors/tokens or prompting automatic login.
- Local indicator warmup/probability/score must not be confused with provider fields.

### Task 1: Provider contract
- [x] Add failing synthetic tests for only allowed tools, explicit range/chunk limits, completed-bar/interpolated normalization, source identity, invalid OHLC and auth failure.
- [x] Implement pa_lens/robinhood.py with injected readonly transport, dynamic external infra loading, fetch/quote results and per-batch provenance/quality.
- [x] Run provider tests and review (13 synthetic tests, independent review).

### Task 2: Required daily swing timeframe and analytics
- [x] Support real daily PA with XNYS calendar, conservative finality, continuity across holidays and missing-session reset; disable intraday-only detectors.
- [x] Add local EMA/RSI calculation with visible method/warmup and provenance separation; no calibrated score.
- [x] Test causal prefixes, gaps/resets and sources.

### Task 3: CLI/journal/UI integration
- [x] Fix Darwin database flock/SQLite collision using an inode-keyed private sidecar lock, retaining alias/concurrency protection.
- [x] Persist acquisition quality/provenance; unknown interpolation always ready=false, including restart and direct replay.
- [x] Add fetch/poll-robinhood as primary acquisition with configurable symbols/range/interval; restrictive loop ingests closed noninterpolated observations, revision audit, transport health.
- [x] Present local analytics separately from raw/provider data, document legacy opt-in compatibility and unsupported periods.
- [x] Run full tests, independent review and actual read-only SOXL recent/known-day plus all-interpolated old sample.

### Task 4: Publish
- [x] Refresh bilingual README, contract/schema/provenance and migration notes, exact verified limits and live evidence.
- [ ] Scan private data/secrets, commit/push authorized public repository, verify exact CI.
