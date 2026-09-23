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

## Testing Commands
```bash
# Run unit and integration suite
python -m unittest discover tests

# Run golden business CI evaluation gate
python -m unittest tests/eval/test_golden_eval_gate.py

# Linting
ruff check .
```
