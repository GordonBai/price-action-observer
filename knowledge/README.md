# Agent-friendly PA knowledge base / PA 研究知识库

Start with [INDEX.md](INDEX.md). This is a curated **44-concept, 26-source research subset**, not complete Brooks coverage, verified trading advice, or a list of implemented detectors. Source review refers to work recorded by this project's research contributors. Some sources were read as full transcripts/PDF charts, others only selected or search-indexed passages. Those distinctions are preserved per source.

## Agent retrieval workflow

Run from the repository root (the script also works by absolute path from another cwd):

```sh
python knowledge/kb.py validate
python knowledge/kb.py search '双底'
python knowledge/kb.py search MM
python knowledge/kb.py search 'risk' --category risk
python knowledge/kb.py show micro-gap
python knowledge/kb.py render --check
python -m unittest discover -s tests -p test_knowledge.py -v
```

1. Search an English/Chinese alias. Results are JSON ordered by exact ID/alias first, then deterministic lexical match. Rank is **not confidence**. This is not semantic/vector search; empty or unknown queries return `[]`.
2. Use `show ID` to retrieve the whole card **and source metadata**. Do not answer from title alone.
3. Read `context`, `counterexample`, `causal_constraints` and `open_questions` alongside `summary`.
4. Follow source URL and locator when a stronger claim needs verification. Page numbers refer to **PDF pages**, including cover, not slide numbers. Indexed excerpts are not full-page review; transcripts are not video viewing.
5. Cite the source and state unresolved evidence. Teaching odds are not model probabilities. Research coverage is independent of [implementation coverage](../docs/COVERAGE.md).

Examples of important distinctions:
- `micro-gap`: cannot be confirmed on the middle bar before its following bar exists.
- `double-bottom`: Brooks test/flag definitions and classical neckline-confirmed reversal definitions differ.
- `measured-move`: multiple anchor families, not one universal formula.
- `actual-risk`: final MAE is hindsight, not available for initial sizing.
- `second-entry`: recorded as a concept with counting/reset rules still unresolved, not as a finished detector.

## Files and data contract

- `concepts.json`: canonical source registry and cards. UTF-8, schema_version 1.
- `kb.py`: offline retrieval, referential/content validation and index rendering; Python standard library only. Does not import or call `pa_lens`.
- `INDEX.md`: generated readable view, including sources, gaps and graph links.
- `DESIGN.md`: scope and architecture decisions.

Each concept has a stable lowercase ID, bilingual aliases, category, original summary, context, counterexample, causal constraints, unresolved questions, source references with locators, related concept IDs, and separate evidence/implementation statuses. Each card also has a code_mapping with audited paths/symbols, source-file hashes, scope limitations and audit date. This is a snapshot: compare the recorded hash with the current file before treating the mapping as current. No mapping means no dedicated implementation, except methodology-only cards. Experimental three-push candidates are explicitly not parabolic-wedge detectors. Each source has an HTTPS URL, title, review date/method/scope, limitations and license caution. `source_reviewed_unvalidated_on_soxl` means a source was reviewed, **not** that all its claims were accepted or its trading rules were empirically validated.

The CLI validates nonempty required fields, status enums, reference integrity and duplicate IDs before querying. Validation does not establish that a claim is true, that a URL remains online, or that a pattern is profitable. No runtime network calls or LLM-generated gap-filling occur.

## Adding knowledge without adding trading rules

1. Read the original legal source; record exact method and scope, including unreviewed media/figures.
2. Add a source entry if needed; add/update an **original concise paraphrase** card with a counterexample and explicit unresolved items.
3. Audit code support separately: `not_implemented`, `partial_engineering_approximation`, `experimental_candidate_only`, `experimental_observation_only` or `methodology_only`. Update code_mapping honestly, never infer implementation from research. The `research_conclusion` is separate from explicitly marked `engineering_interpretation` guidance.
4. Preserve IDs, check related links, and test retrieval aliases.
5. Regenerate and verify:

```sh
python knowledge/kb.py validate
python knowledge/kb.py render > knowledge/INDEX.md
python knowledge/kb.py render --check
python -m unittest discover -s tests -p test_knowledge.py -v
```

Do not copy course videos, textbooks, paid content or third-party full text into this directory. Public accessibility is not an open-source license. Underlying source rights remain with their owners. This directory contains original summaries and metadata only. The complete course index is a research backlog, not watched-course coverage; no index item is silently converted into a sourced card.

## Evidence-role and retrieval safeguards

Source references have `support_role`: `concept_support`, `counterexample_support`, or `coverage_only`. A course index is allowed only as coverage metadata, never conceptual evidence. Every concept card must have at least one non-index source with `concept_support`; coverage-only or counterexample-only references cannot substantiate a card. All five official public samples have full official English captions read: 12A, 20AB MM, 2017 Trading the Open, 37AB How to Trade and 42A Climactic Reversals. Total: 2,109 cues. Only 21 sampled frame points were inspected (13 + 2 + 3 + 1 + 2), not continuous video. Audio heard: none. Complete continuous audiovisual reviews: 0/5. These excerpts are not the complete paid chapters. Source media_review metadata records caption hashes, actual sample times and explicit false audio/continuous-review flags; no captions or media are redistributed.

Aliases mean the same concept; `related_search_terms` only means a nearby topic. “突破失败” retrieves failed-failure as related context, not as an asserted synonym. “三推” can retrieve the parabolic-wedge card, but arbitrary three pushes are not asserted to be parabolic. Read the returned card and its code limitations. Search includes causal constraints, while generated Markdown exposes source role, date, scope, method, limitations and license status.

See [COVERAGE_AUDIT.md](COVERAGE_AUDIT.md) for newly checked gaps and what remains unreviewed. Claim layers explicitly separate source paraphrase, project synthesis and unverified questions. Public-source supplementation does not authorize new detector rules.

Compatibility fields `research_conclusion` and `engineering_interpretation.constraints` must exactly match canonical `summary` and `causal_constraints`; validation rejects drift. Update both copies together until a future schema migration removes the duplicates. Barbwire is a related subtype, not a strict synonym for every tight trading range.
