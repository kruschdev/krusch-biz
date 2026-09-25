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
8. **MCP Canonical Consolidation & Anti-Tool-Bloat Standard**:
   - **6 Canonical Tools**: To prevent context window bloat (~950 tokens vs ~3,500 tokens) and tool routing confusion on local 7B/14B models, `TOOLS_CATALOG` exposes strictly 6 high-leverage canonical tools: `contract_intelligence`, `manage_deal`, `vendor_portfolio`, `accounts_receivable`, `commercial_drafting`, and `document_pipeline`.
   - **Backwards-Compatible Dispatch**: The MCP dispatcher maintains transparent routing for both the 6 canonical tools and all 16 legacy granular tool names, preventing breaks in existing integrations.
   - **Separation of Concerns**: The database and FastAPI routes handle arithmetic, relational state, and ground truth; the agent and MCP layer handle reasoning and communicative interface.

9. **Precedence Graph Hardening, Draft Isolation & The Join**:
   - **Confirmed Edges Only**: Auto-extracted relations remain `status='proposed'` and never silently control DAG traversal; only human-confirmed edges (`status='confirmed'|'accepted'`) control.
   - **Draft Isolation**: Unexecuted drafts (`execution_status='draft'`) cannot defeat, supersede, or amend executed agreements.
   - **Hierarchical Governance**: Master agreements (MSAs) outrank SOWs/schedules on general governance provisions unless an explicit clause-level carve-out exists.
   - **The Join (`POST /conflicts/contract-vs-statute`)**: Directly compares controlling contract clause slots against statutory floors and ceilings (e.g., California AB 12 security deposit caps, Civ. Code § 1954 24-hr entry notice floor).
   - **Audit Trace**: Immutable `ResolutionTraceRecord` with cryptographic timestamps persisted to the database on every consult.

10. **Sovereign 5-Verb Gateway MCP Router (`src/mcp/gateway.py`)**:
    - **Prompt Token Budget**: Single consolidated gateway strictly constrained to <450 prompt tokens (~428 tokens) for local 7B/14B inference without prompt bloat.
    - **Core Verbs**: `ask_law`, `ask_biz`, `check_compliance`, `ingest`, `purge`.
    - **Orchestrator Invariants (`docs/ORCHESTRATOR_SPEC.md`)**:
      - Canonical `matter_ref` ↔ `deal_ref` cross-domain mapping.
      - Never union law and contract vector tables (clean schema separation).
      - Mandatory `as_of_date` on every consult.
      - Deterministic typed number evaluation over LLM math.

## Testing Commands
```bash
# Run full unit, integration, precedence graph, The Join, and MCP test suite (145 tests)
pytest tests

# Run precedence graph and draft isolation tests
pytest tests/test_precedence.py

# Run The Join statutory compliance tests
pytest tests/test_the_join.py

# Run 5-verb Gateway MCP router tests
pytest tests/test_gateway_mcp.py

# Run canonical 6-tool MCP server tests
pytest tests/test_mcp.py

# Run commercial operations and DraftPro test suites
pytest tests/test_business_ops.py tests/test_business_ocr.py tests/test_business_templates.py

# Run commercial tagger and deal evidence tests
pytest tests/test_commercial_tagger.py tests/test_deal_evidence.py

# Run golden business CI evaluation gate
pytest tests/eval/test_golden_eval_gate.py

# Linting
ruff check .
```

