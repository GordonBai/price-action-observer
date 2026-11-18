# Native-first Interpretation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. User delegated design and execution; do not ask architecture questions.

**Goal:** Native-first current indicator interpretation without local fallback or historical backfill.
**Architecture:** Independent current-snapshot interpreter consumes latest original bar and separately received native evidence. Pure candle structures remain unchanged. Local EMA-dependent observations remain labeled audit diagnostics, excluded from primary presentation.
**Tech Stack:** Python, SQLite, existing dashboard/CLI.
**Spec:** This short plan includes the implementation contract below.

## Global Constraints
No orders. No local fallback. Native source/warmup unknown stays explicit. EMA20 requires period20, RSI14 requires14. Exact matching symbol/timeframe/bounds/adjustment and bar-effective timestamp. Late receipts cannot become earlier interpretations. Historical focus/replay has no reconstructed native interpretation.

## Review Focus
Receipt after decision; period/timeframe mismatch; stale point despite fresh receipt; error/undefined/partial; local EMA events hidden from primary but retained in audit.

### Task 1: Current native interpreter
- [x] Red tests for strict matching/receipt/freshness/period/no-fallback/historical unavailable.
- [x] Add native_interpretation.py, expose result in Journal snapshot and terminal.
- [x] Mark local EMA families diagnostic and filter primary projector.
### Task 2: UI and verification
- [x] Add native-first context panel, hide current context during historical focus/disconnect.
- [x] Update identity, docs and tests; full suite and independent review, no push here.
