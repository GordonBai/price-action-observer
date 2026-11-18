# Native indicator implementation plan

Base: v0.5 public 8bb930e. Existing authorized workflow remains read-only and Robinhood-first.

1. [x] Read actual live indicator descriptor and user-provided infra manual; implement provider validation/normalization for all18 with test-first contracts and provenance. Independent review.
2. [x] Add configurable selection/parameter JSON, bounded sequential collection with partial-result statuses, journal snapshot persistence, terminal summary and separate dashboard native-indicator view. Test timestamp/receipt/history focus and restart. Do not change PA rule calculations.
3. [x] Execute actual SOXL today5m end-to-end all18 read, inspect terminal and browser, report exact availability/warmup/input-quality limits. Preserve private raw captures.
4. [ ] Update bilingual docs/migration and source-code identity, run full suite and independent review, scan complete publication history, ordinary authorized push and verify exact GitHub CI.
