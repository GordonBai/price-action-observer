# Robinhood-first Observation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Active, auditable Robinhood market-data acquisition with local indicators and PA observations.
**Architecture:** Restricted provider wraps existing authenticated CodexMarketTransport. Acquisition/normalization is separate from local analytics and observation engine; journal preserves first-received evidence and audits corrections.
**Tech Stack:** Python stdlib, external installed robinhood trading infra, SQLite, existing HTML dashboard.
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
- [ ] Add failing synthetic tests for only allowed tools, explicit range/chunk limits, completed-bar/interpolated normalization, source identity, invalid OHLC and auth failure.
- [ ] Implement pa_lens/robinhood.py with injected readonly transport, dynamic external infra loading, fetch/quote results and per-batch provenance/quality.
- [ ] Run provider tests and review.

### Task 2: Timeframe and analytics
- [ ] Define truthful supported pattern intervals and daily behavior; test exact timestamp/session contracts.
- [ ] Add local EMA/RSI calculation with visible method/warmup and provenance separation; no calibrated score.
- [ ] Test causal prefixes, gaps/resets and sources.

### Task 3: CLI/journal/UI integration
- [ ] Add fetch/poll-robinhood as primary acquisition with configurable symbols/range/interval; restrictive loop ingests closed noninterpolated observations, revision audit, transport health.
- [ ] Present local analytics separately from raw/provider data, document legacy opt-in compatibility and unsupported periods.
- [ ] Run full tests, independent review and actual read-only SOXL recent/known-day plus all-interpolated old sample.

### Task 4: Publish
- [ ] Refresh bilingual README, contract/schema/provenance and migration notes, exact verified limits and live evidence.
- [ ] Scan private data/secrets, commit/push authorized public repository, verify exact CI.
