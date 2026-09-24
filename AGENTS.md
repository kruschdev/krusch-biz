# KruschBiz — AI Agent Operating Manual

## Purpose & Scope
KruschBiz is an on-premise, air-gapped corporate intelligence engine and versioned commercial contract graph. It acts as the business/corporate peer to `krusch-law` and consumes `krusch-nexus` as its document ingestion spine.

## Key System Invariants
1. **Loopback Only**: All services bind to `127.0.0.1`. Never expose raw ports to `0.0.0.0` in production without authentication and firewall.
2. **Ports Allocation**:
   - Backend API: `8086`
   - Frontend UI: `8506`
   - PostgreSQL (pgvector): `5436`
   (Avoids collisions with KruschLaw 8085/8505/5435 and KruschNexus 8000/8002).
3. **Dual Dialect Resilience**:
   - Production uses PostgreSQL 16 + pgvector.
   - Unit tests, CI, and local dev automatically fall back to in-memory SQLite with serialized JSON vectors. Always ensure code functions identically under both dialects.
4. **KruschNexus Integration**:
   - Document ingestion must route through `krusch_nexus.parsers.parse_document` and `krusch_nexus.chunking.chunk_document_pages`.
   - Never strip physical page numbers (`p. N`) or section headers from chunk metadata.
5. **Commercial Assertion Grounding**:
   - Any AI-generated brief must be audited at the proposition level.
   - Guardrail: Refuse to draft briefs when zero governing agreements exist in the corpus (`CANNOT_DRAFT_WITHOUT_AUTHORITIES`).

6. **Commercial Ensemble Tagging & Semantic Recall Invariants**:
   - **Ensemble Merge Rule**: When processing chunks in `src/backend/tagger.py`, deterministic slot extractions (`net-30`, `uptime-99.9pct`, `cap-12mo`, `sec-12`) MUST be merged with LLM semantic tags. Controlling numbers must NEVER be dropped or omitted.
   - **Canonical Topics**: Map contract chunks into the 13 canonical topics defined in `taxonomy.py` (`PAYMENT_TERMS`, `LIABILITY_CAP`, `SLA_UPTIME`, etc.).
   - **Dual-Path Boosting**: In `retrieve_deal_evidence`, candidate chunks matching requested tags receive a +20% score boost (`score * 1.20`) alongside dense vector cosine similarity and BM25 lexical ranking.
   - **Pydantic Serialization**: SQLite/Postgres text columns storing JSON tags must utilize `@field_validator("tags", mode="before")` on Pydantic schemas (e.g., `DealEvidenceItem`) to transparently deserialize raw JSON strings into typed string lists.
   - **Air-Gapped Sovereign Model**: Use local Ollama `qwen2.5-coder:7b` with a 15.0s timeout and immediate deterministic fallback. Zero external network calls.

7. **Commercial Operations & DraftPro Invariants**:
   - **Contract Portfolio**: Track vendor agreements, expiration dates, renewal terms, and auto-renew flags with proactive alert thresholds (e.g. 30/60/90 days).
   - **Invoicing & Accounts Receivable**: Dual-storage JSON line items, automated subtotal, tax rate, and total calculation. Support status lifecycle (`draft`, `sent`, `paid`, `overdue`, `cancelled`) with automated aging breakdown (current, 1-30d, 31-60d, 61-90d, 90d+).
   - **Invoice & Document OCR Parsing**: Safe heuristic regex parser with date and currency sanitization, MIME validation, 20MB file cap, and confidence scoring.
   - **DraftPro Commercial Templates**: 5 core templates (`commercial_nda`, `master_services_agreement`, `statement_of_work`, `independent_contractor`, `commercial_demand_letter`). Strict field validation, dynamic math computation (e.g. demand letter total due), and legal revision engine.
   - **Scope Boundaries**: Explicitly excludes personal/fleet expense tracking and mileage calculators (retained only in personal/fleet modules, omitted from KruschBiz per architecture directive).

## Testing Commands
```bash
# Run full unit, integration, tagger, business ops, OCR, template, and security test suite (94 tests)
pytest tests

# Run commercial operations and DraftPro test suites
pytest tests/test_business_ops.py tests/test_business_ocr.py tests/test_business_templates.py

# Run commercial tagger and deal evidence tests
pytest tests/test_commercial_tagger.py tests/test_deal_evidence.py

# Run golden business CI evaluation gate
pytest tests/eval/test_golden_eval_gate.py

# Linting
ruff check .
```

