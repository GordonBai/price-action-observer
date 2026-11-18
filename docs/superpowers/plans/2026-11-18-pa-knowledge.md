# PA Knowledge Base Implementation Plan

> For agentic workers: execute the independently delegated plan in this thread; no pattern changes.

**Goal:** searchable, provenance-aware PA research cards in the same repository.
**Architecture:** JSON source of truth, deterministic Markdown index, Python stdlib CLI.
**Tech Stack:** Python 3 standard library, JSON, Markdown, unittest.
**Spec:** knowledge/DESIGN.md

## Global Constraints
No third-party full text/media, no detector imports, no claim of complete coverage or verified edge.

## Review Focus
Unknown aliases; dangling source/related references; incomplete provenance; accidental implementation claims; stale generated index.

## Tasks
- [x] Write independent tests for integrity, retrieval, CLI and generated index; run and observe failure.
- [x] Populate original concise concept cards and source metadata from already-read research, preserving unresolved items.
- [x] Implement knowledge/kb.py load, validate, search, show and render using no external dependencies.
- [x] Generate INDEX.md; document retrieval workflow and limitations in knowledge/README.md.
- [x] Run independent tests and full existing unittest suite, report exact results to coordinator.
