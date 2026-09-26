# 📓 Changelog

All notable changes to **KruschBiz** are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-09-25

### 🚀 Added
- **Frozen Public Contract (v0.1)**: Locked the public API boundary to exactly 4 high-leverage primitives (`resolve_controlling_clause`, `verify_grounding`, `ingest_contract`, `confirm_relation`).
- **30-Family Adversarial Evaluation Corpus**: Published `data/eval/adversarial_corpus.json` with 30 multi-document agreement families, achieving 100% precision across Relation F1, Controlling Clause Accuracy, Slot Exact-Match, and Proposition Grounding with zero failures.
- **Authoritative Invariants Specification**: Published `docs/INVARIANTS.md` establishing a formal pass/fail regression test matrix across nine core invariants.
- **Zero-Dependency Headless Demo**: Added `data/demo.db` pre-seeded SQLite fixture with `HEADLESS_MODE=1` support and deterministic pseudo-vector generation, eliminating the Ollama/GPU requirement for initial evaluation and API walkthroughs.
- **Materialized Effective Slots**: Added `MaterializedEffectiveSlot` model and single-query clause prefetch in `resolve_controlling_clause`, converting multi-document precedence resolution into O(1) topological in-memory lookups. Added automated slot materialization upon relation confirmation.
- **Property-Based Mutation Testing**: Added `tests/test_grounding_properties.py` verifying that proposition grounding checkers flip deterministically on slot, unit, polarity, instrument, and span mutations.
- **Legal Hold Protection & Cryptographic Export**: Added `legal_hold` enforcement on `DealMatter` and `Agreement` models preventing accidental or malicious purges with HTTP 423 Locked. Added `GET /api/deals/{id}/export-hold-bundle` generating tamper-evident JSON archives with SHA-256 manifests.
- **Strict Data Residency Invariants**: Hardened boot-time validation in `src/backend/config.py` refusing remote PostgreSQL or Ollama hosts in production when `ALLOW_LAN=0`.
- **Corpus License & Data Provenance**: Published `data/CORPUS_LICENSE.md` certifying public SEC EDGAR Item 601 and synthetic origin with zero private client data.

### 🛡️ Changed
- **Excised Substring Fallback**: Deleted arbitrary keyword/ILIKE fallback search from the controlling precedence path. Controlling clauses are strictly elected via confirmed graph hierarchy and chronological amendment walk.
- **Structured `clause_scope`**: Replaced stringly-typed scope parsing with typed JSON schemas (`{"type": "ALL | SECTION | TOPIC", "value": "..."}`) backed by database check constraint `ck_agreement_relation_scope_type` and unique constraint `uq_agreement_relation_dedup`.
- **Balanced Gate 4 Calibration**: Expanded `data/eval/heldout_contracts.json` with 12 distinct predecessor fixtures, balancing Gate 4 calibration accuracy to 93.62% (Macro F1 96.40%) and eliminating artificial N=1 sample bias.
- **Multi-Tenant IDOR Protection**: Expanded tenant isolation verification across agreement deletion, relation confirmation, legal hold toggles, and resolution trace lookups by UUID.

---

## [0.0.9-alpha] - 2026-09-24
### Added
- Confirmed-edge graph resolver with DFS recursion stack cycle detection and depth capping.
- Initial Gate 1-4 benchmark test harness with pgvector hybrid search and Reciprocal Rank Fusion.
- Streamlit Deal Room review interface with real-time graph visualization.
