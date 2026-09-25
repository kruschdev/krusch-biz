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

7. **Confirmed-Edge Relational Graph & Draft Isolation Invariants**:
   - **Confirmed Edges Only**: Auto-extracted relations remain `status='proposed'` and never silently control DAG traversal; only human-confirmed edges (`status='confirmed'|'accepted'`) control.
   - **Draft Isolation**: Unexecuted drafts (`execution_status='draft'`) cannot defeat, supersede, or amend executed agreements.
   - **Hierarchical Governance**: Master agreements (MSAs) outrank SOWs/schedules on general governance provisions unless an explicit clause-level carve-out exists.
   - **Audit Trace**: Immutable `ResolutionTraceRecord` with cryptographic timestamps persisted to the database on every consult.

8. **MCP Catalog & Sovereign Gateway Standards**:
   - **Core Domain MCP Tools**: `src/mcp/server.py` exposes strictly 4 core domain tools: `contract_intelligence`, `manage_deal`, `ingest_contract`, and `verify_grounding`. Zero ops, invoicing, or legacy drafting tools.
   - **Sovereign 5-Verb Gateway MCP Router (`src/mcp/gateway.py`)**: Consolidated cross-domain router strictly constrained to <450 prompt tokens (~428 tokens) for local 7B/14B inference (`ask_biz`, `ask_law`, `check_compliance`, `ingest`, `purge`).
   - **Orchestrator Invariants (`docs/ORCHESTRATOR_SPEC.md`)**:
     - Canonical `matter_ref` ↔ `deal_ref` cross-domain mapping.
     - Never union law and contract vector tables (clean schema separation).
     - Mandatory `as_of_date` on every consult.
     - Deterministic typed number evaluation over LLM math.

## Testing Commands
```bash
# Discover canonical test count
pytest --collect-only -q

# Run full core test suite
pytest tests

# Run precedence graph and draft isolation tests
pytest tests/test_precedence.py

# Run The Join statutory compliance tests
pytest tests/test_the_join.py

# Run 5-verb Gateway MCP router tests
pytest tests/test_gateway_mcp.py

# Run canonical 4-tool MCP server tests
pytest tests/test_mcp.py

# Run commercial tagger and deal evidence tests
pytest tests/test_commercial_tagger.py tests/test_deal_evidence.py

# Run golden business CI evaluation gate
pytest tests/eval/test_golden_eval_gate.py

# Linting
ruff check .
```

