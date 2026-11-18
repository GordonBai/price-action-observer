# PA research knowledge base design

Authorized scope: independently build an agent-friendly research knowledge base; architecture delegated. JSON is canonical; stable IDs, bilingual aliases, explicit source-reading provenance, unresolved questions, causal constraints and related concepts support retrieval. Markdown is a generated view. Standard-library CLI supports search, show, validate and render. No embeddings, remote services, dependency installation or detector coupling.

Alternatives considered: Markdown-only is easy to edit but harder to validate; a vector database adds dependency and opaque ranking. JSON + deterministic lexical retrieval is the chosen small, auditable baseline. This is not exhaustive Brooks coverage, a calibrated trading system, or permission to implement patterns. No original course files or third-party full texts are included.

Acceptance: aliases retrieve relevant cards; unknown/empty queries do not invent answers; every source reference resolves to an explicit locator and reading method; graph references resolve; generated index matches JSON; malformed records fail validation; CLI works outside repository cwd. Research coverage never implies code coverage.
