# 📓 Changelog

All notable changes to **KruschBiz** are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-09-27

### 🚀 Added
- **Physical Citation Spine Coordinates (INV-11)**: Established full architectural parity with KruschLaw v0.6.0 and KruschNexus document ingestion spine.
- **ORM Coordinate Schema**: Added `page_number`, `printed_page`, `bbox` (bounding box `[x0, top, x1, bottom]`), `char_start`, `char_end`, and `extra_metadata` (`JSONType`) to `Clause`, `CommercialClauseVector`, and `DealEvidence` models with idempotent PostgreSQL migrations.
- **End-to-End Coordinate Propagation**:
  - `src/backend/ingest.py`: Extracted physical citation coordinates from KruschNexus chunks during ingestion and persisted to PostgreSQL/SQLite tables.
  - `src/backend/rag.py`: Updated hybrid RRF search query, candidate population, and evidence formatting to return all 6 coordinate fields.
  - `src/backend/resolver.py`: Enriched `resolve_controlling_clause` across single terminal, SOW, and MSA winner branches to pass physical citation coordinates in `controlling_clause`.
  - `src/backend/main.py`: Enriched `ClauseResponse` and `DealEvidenceItem` Pydantic schemas with nullable coordinate attributes.
- **Regression Test Coverage**: Added `test_property_6_physical_citation_spine_coordinate_persistence` in `tests/test_grounding_properties.py` and `test_06_deal_evidence_and_clause_coordinate_propagation` in `tests/test_nexus_integration.py` (200 passing tests total).
- **Frozen Demo DB Rebuilt**: Regenerated `data/demo.db` fixture with physical citation spine coordinates for offline development and testing.

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
