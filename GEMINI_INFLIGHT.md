# GEMINI_INFLIGHT — KruschBiz

> Last updated: 2026-09-24

## Active Environment & Nodes
- Primary node: `krusch` (Central Orchestrator & Dev Station)
- Python environment: `/home/krusch/homelab/projects/krusch-law/.venv/bin/python3`
- Database: SQLite in-memory / local SQLite WAL + PostgreSQL `kdcode:5432` / `kruschserv:5436`

## Currently Modifying
- Completed all 8 priorities of the code-backed improvement plan.
- Committed in git: `39be255` (`feat(core): implement 8-priority architectural hardening across graph, grounding, and retrieval`).

## Fragile / Don't Touch
- `src/labs/` — Non-core commercial operations (`business_ocr.py`, `business_router.py`, `business_templates.py`) quarantined behind `ENABLE_BUSINESS_OPS=False`. Do not un-quarantine without explicit user instruction.
- `AuditLog` (`src/backend/db.py`) — Immutable append-only audit trail enforced via SQLAlchemy event listeners (`before_update`, `before_delete`) raising `PermissionError`.
- `get_embeddings_batch` (`src/backend/rag.py`) — Never re-introduce constant mock vector fallback (`[0.05] * 1024`) for drafting. It must fail-closed with `RetrievalError("CANNOT_DRAFT_EMBEDDINGS_UNAVAILABLE")`.

## Active Background Processes
- `krusch-git` snapshotting to PostgreSQL (`sync_to_pg.js`).

## Task-Specific Constraints
- Zero-constant-vector invariant: Drafting on fake or constant mock vectors is strictly prohibited.
- Zero-trust tenant isolation: Tenant IDs in `X-Tenant-ID` headers must match API key bindings (`tenant_id:key_secret`), or request is rejected with HTTP 403 Forbidden.
- Relation cycle guard: Transitive DAG walks cap depth at 32 with cycle detection.
- Unified retrieval scoring: All candidates must be scored by `score_retrieval_candidate` in Python to guarantee scoring parity across SQLite and Postgres.

## Last Session
- Completed all 8 priorities from the code-backed improvement plan.
- 129 / 129 tests passing across full pytest suite.
- Pre-commit invariant audit: `NO_NUDGES_REQUIRED`.
- Published raw scorecard artifact: `data/eval/scorecard.json` (Gate 3 Held-Out Recall@5: 100%, 0 priority inversions, 100% macro precision).
- Committed with hash `39be255`.

## Open Questions
- None. Core graph, layered grounding, retrieval scoring, and tenant isolation are fully realized in running code.

## Discovered Issues
- Query expansion was found to degrade Recall@1 (from 91.67% down to 83.33%) and MRR (from 0.958 down to 0.917) on held-out contracts by injecting generic legal distractor keywords. Defaulted `expand_query=False` in `retrieve_clauses` and cached expansions with LRU.

## Visual & Test Verification Status
- Full Pytest Suite: 129 passed in 4.62s.
- Adversarial Grounding: 16 / 16 adversarial tests passed.
- Security Hardening: 8 / 8 tests passed (tenant header spoofing rejection, sliding window rate limits, magic byte validation, mock vector refusal).
- Multi-Gate Evaluation Harness: 4 / 4 gates passed (`data/eval/scorecard.json`).

## Next Steps
- [x] Priority 0: Transitive DAG relation walking, candidate text extractor, stable clause_uid.
- [x] Priority 1: Layered assertion grounding checker and 16 adversarial tests.
- [x] Priority 2: Tighten taxonomy slots with context guards and add tagger LRU cache with JSON repair.
- [x] Priority 3: Unified Python retrieval scorer, eliminated constant vector mock fallback, evaluated query expansion.
- [x] Priority 4: Atomic multi-table purges and immutable append-only audit trail.
- [x] Priority 5: Gate 3 primary held-out evaluation and raw scorecard publishing.
- [x] Priority 6: Scope quarantine of commercial ops under `src/labs/` behind `ENABLE_BUSINESS_OPS`.
- [x] Priority 7: Tenant-bound API keys, pre-spool magic byte validation, and rate limiters.
- [x] Priority 8: POST resolver endpoints, enriched consult responses, and lean 4-tool MCP surface.
- [ ] Push commit `39be255` to remote repository if desired (`git push origin main`).
