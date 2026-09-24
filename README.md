# 💼 KruschBiz

> **Sovereign Corporate Intelligence Engine & Commercial Contract Graph**  
> *Private corporate contract retrieval, relational contract graph walking, commercial assertion-level grounding verification, and audit-logged executive decision intelligence using on-premise open-weight models and the sovereign KruschNexus ingestion spine.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 0.1.1](https://img.shields.io/badge/Version-0.1.1-green.svg)](https://github.com/kruschdev/krusch-biz)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector%2016-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Tests: 100 Passing](https://img.shields.io/badge/Tests-100%20Passing-brightgreen.svg)](tests/)
[![CI Gates: Passing](https://img.shields.io/badge/CI%20Gates-3%2F3%20Passing-brightgreen.svg)](.github/workflows/ci.yml)

---

> [!WARNING]
> **Research Prototype & Corporate Governance Scope (Read Before Evaluating)**:  
> KruschBiz is an open-source technical prototype exploring sovereign on-premise corporate intelligence and retrieval-augmented generation. It is **NOT** a law firm, does **NOT** provide legal advice, and does **NOT** replace certified legal counsel or corporate auditors.
> - **Semantic Similarity ≠ Governing Obligation**: Cosine retrieval identifies textually similar provisions; it does not determine binding precedence, execution status, or legal enforceability. KruschBiz resolves this via explicit graph edges (`AMENDS`, `SUPERSEDES`, `INCORPORATES`) and a controlling-document resolver.
> - **Execution Status & Amendments**: While KruschBiz tracks temporal dates, amendments, and superseded relations within its local graph, operators must ensure fully executed agreements are ingested.
> - **Confidentiality & Storage Boundary**: Default port bindings (`127.0.0.1`) restrict services strictly to loopback. Deal room exhibits and retrieved clauses remain entirely on-premise. Sovereign trade secret protection requires operator-enforced host storage encryption (LUKS / FileVault) and network isolation.
> - **Mandatory Human Verification**: All generated drafts are explicitly marked `review_required: true` and `provisional_work_product: true`. Outputs must be independently verified by admitted counsel and corporate officers prior to execution or reliance.

---

## 🏛️ Why KruschBiz?

Enterprise legal departments, corporate procurement teams, and M&A executives face an existential dilemma:
1. **Public Cloud LLMs & SaaS Vector DBs**: Expose confidential deal terms, proprietary pricing, trade secrets, employee records, and acquisition targets to third-party cloud sub-processors and potential training pools—violating non-disclosure agreements (NDAs) and corporate governance mandates.
2. **Generic RAG Loss of Hierarchy**: Standard vector pipelines chunk contracts into arbitrary 500-token blocks, stripping physical page numbers, clause hierarchies, and amendment relations. A 2021 expired amendment can easily outrank a controlling 2025 Master Services Agreement.
3. **Plausible Hallucinations**: Standard LLM generation frequently hallucinates terms (e.g. asserting "Net 45" when the contract specifies "Net 30", or inventing phantom section numbers).

**KruschBiz** solves this with:
- **Relational Contract Graph**: Explicit instrument nodes (`agreements`), clause nodes (`clauses`), and typed relation edges (`AMENDS`, `SUPERSEDES`, `INCORPORATES`, `SCHEDULE_OF`, `CARVES_OUT`).
- **Controlling Document Resolver**: Graph-walking algorithm that determines the controlling instrument and clause given `(counterparty, topic, as_of_date)`.
- **Closed Taxonomy & Structured Slot Extraction**: Extracts canonical commercial slots (`net_days`, `late_interest_pct`, `uptime_pct`, `cap_period_months`, `notice_hours`) directly into JSON columns at ingest.
- **Assertion-Level Proposition Grounding Scanner**: Verifies generated claims using exact span overlap, slot value assertion, and citation existence, reporting a 4-way failure taxonomy (`VERIFIED`, `INVENTED_CLAUSE`, `DIVERGENT_TERM`, `SUPERSEDED_TERM`).
- **Air-Gapped Sovereign Ingestion Spine**: Standalone parser and chunker with optional KruschNexus OCR integration, enforcing MIME magic bytes verification and chunk DOS limits.

---

## 🚀 Core Capabilities

* 🔒 **Sovereign Air-Gapped Topology**: Default loopback bindings (`127.0.0.1:8086`, `127.0.0.1:8506`), code-level loopback verification, zero external telemetry, and mandatory API keys in non-development modes.
* 🕸️ **Relational Contract Graph & Controlling Resolver**:
  * Explicit database models: `agreements`, `clauses`, and `agreement_relations`.
  * Foreign key constraints with cascading deletes (`ON DELETE CASCADE` / `SET NULL`).
  * `resolve_controlling_clause(counterparty, topic, as_of_date)` walks amendment chains and SOW schedules to identify controlling terms.
  * `detect_contract_conflicts(counterparty, as_of_date)` surfaces diverging terms across live operative agreements before LLM synthesis.
* 🎯 **Closed Commercial Taxonomy & Open Structured Slots**:
  * 13 canonical commercial topics (`PAYMENT_TERMS`, `LATE_FEE`, `LIABILITY_CAP`, `LIABILITY_CARVE_OUT`, `INDEMNITY`, `SLA_UPTIME`, `SLA_CREDIT`, `DATA_PROTECTION`, `BREACH_NOTIFICATION`, `AUDIT_RIGHTS`, `TERMINATION_CONVENIENCE`, `MOST_FAVORED_NATION`, `GOVERNING_LAW`).
  * Structured slot extraction into JSON columns at ingest (`net_days`, `uptime_pct`, `late_interest_pct`, `cap_period_months`, `notice_hours`, `notice_days`).
* 🛡️ **Assertion-Level Grounding & Failure Taxonomy**:
  * Constrained claim schema (`claim_id`, `sentence`, `cited_authority`, `status`, `failure_mode`, `span_overlap_pct`, `slot_divergence`).
  * Verifies each proposition via text span overlap and structured slot assertions. LLM is used strictly as a tie-breaker.
  * 4-way classification:
    * ❌ **INVENTED_CLAUSE**: Cites a section number or contract instrument that does not exist in the retrieved authorities.
    * ⚠️ **DIVERGENT_TERM**: Cites an operative clause but misstates numeric values or obligations (e.g. draft claims Net 45 when agreement specifies Net 30).
    * 🛑 **SUPERSEDED_TERM**: Cites an instrument superseded or amended by a newer controlling agreement.
    * ✅ **VERIFIED**: Provenance substantiated by exact excerpt from governing contract.
* 🛑 **Agent Refusal Guardrails**:
  * `CANNOT_DRAFT_WITHOUT_AUTHORITIES`: Refuses drafting when zero relevant authorities exist in the graph.
  * `REFUSAL_ALL_AUTHORITIES_SUPERSEDED`: Refuses drafting if all retrieved authorities are superseded or terminated.
* 🌲 **Sovereign Document Ingestion**:
  * Standalone parser adapter supporting PDF, DOCX, TXT, MD, CSV with natural legal boundary chunking.
  * Validates MIME types via file magic bytes (rejects disguised executables or unknown binaries).
  * Max chunk DOS guardrail (`MAX_INGEST_CHUNKS_PER_DOC = 500`).
  * Transactional `IngestJob` state machine (`queued → parsing → extracting_slots → embedding → indexed | failed`).
* 🏢 **Multi-Tenant Isolation**: Enforces `tenant_id` across all queries, agreements, clauses, deal matters, evidence, and audit logs.
* 🏢 **Commercial Operations & Accounts Receivable Engine**:
  * **Contract Portfolio & Expiration Tracking**: Tracks vendor master agreements, SOWs, renewal terms, auto-renew flags, and configurable expiration warning horizons (30/60/90 days).
  * **Invoicing & Accounts Receivable (AR)**: Complete invoicing workflow with structured JSON line items, automated subtotal/tax/total computation, status lifecycle (`draft`, `sent`, `paid`, `overdue`, `cancelled`), and real-time aging bucket breakdown (Current, 1–30d, 31–60d, 61–90d, 90d+).
  * **Document & Invoice OCR Parser**: Heuristic regex parser with currency (`clean_currency_str`) and date normalizers, 20MB file upload guardrail, path traversal protection, and extraction confidence scoring.
  * **DraftPro Commercial Document Generator**: Schema-driven templates for NDAs, Master Services Agreements (MSAs), Statements of Work (SOWs), Independent Contractor Agreements, and Commercial Demand Letters with automated balance calculations and legal revision workflow.
* 🏷️ **Commercial Ensemble Chunk Tagging & Micro-Digests**: Integrated commercial chunk tagger (`src.backend.tagger`) performing an ensemble merge of deterministic contractual slot tags (`net-30`, `uptime-99.9pct`, `cap-12mo`, `sec-12`) with local Ollama (`qwen2.5-coder:7b`) extracting 3–5 lowercase domain tags and 1-sentence micro-digests. Provides automatic deterministic fallback on timeout.
* 🔍 **Dual-Path Commercial Retrieval & Faceted Deal Explorer**: Combines dense vector similarity (`bge-large` 1024-dim) with lexical cover-density RRF, applying an exact tag boost (+20%) and canonical topic filtering (`PAYMENT_TERMS`, `LIABILITY_CAP`, `SLA_UPTIME`, etc.). Features a dedicated faceted evidence explorer in Streamlit (Tab 1) and REST endpoints (`GET /api/deals/{deal_id}/evidence`, `/evidence/tags`, `GET /api/clauses?topic=...&tag=...`).
* 🗑️ **Hard Delete & Regulatory Audit Trail**:
  * `DELETE /api/deals/{deal_id}/hard-delete` permanently purges deals, exhibits, and grounding reports while logging an immutable regulatory audit entry.
* 🔌 **Model Context Protocol (MCP) Server**: Exposes 6 high-leverage canonical tools (~950 prompt tokens) over stdio JSON-RPC to protect local 7B/14B models from tool overload, with full backwards-compatible dispatch across all 16 legacy corporate tools.

---

## 🏷️ Commercial Ensemble Chunk Tagging & Dual-Path Semantic Recall

KruschBiz features a specialized commercial chunk tagging and retrieval pipeline tailored for corporate agreements, SOWs, and M&A due diligence exhibits.

```
                           Raw Contract Chunk
                                   │
                   ┌───────────────┴───────────────┐
                   ▼                               ▼
      Deterministic Slot Extraction     Local LLM Semantic Tagger
     (net-30, uptime-99.9pct, cap, sec)  (Ollama qwen2.5-coder:7b @ 15s)
                   │                               │
          Exact Slot Anchor Tags          Semantic Concepts &
      (e.g., `net-30`, `uptime-99.9pct`)   1-Sentence Micro-Digest
                   │                               │
                   └───────────────┬───────────────┘
                                   ▼
                         Ensemble Tag Union
                   (Deduplicated, Normalized, Grounded)
                                   │
                                   ▼
                   PostgreSQL 16 + pgvector Storage
             (DealEvidence & CommercialClauseVector Schemas)
                                   │
                                   ▼
                      Dual-Path Retrieval Pipeline
    (Dense Vector Cosine + BM25 Lexical RRF + 20% Tag Boost + Topic Filter)
```

### 1. The Commercial Ensemble Tagging Standard
Commercial agreements combine rigid numerical metrics (payment periods, availability commitments, damage caps) with nuanced qualitative obligations (confidentiality, IP assignments, indemnity triggers). An LLM-only tagger frequently captures the abstract concept (e.g. `payment-terms`) but drops the controlling numeric anchor (`net-30`).

KruschBiz resolves this via **Ensemble Tagging** (`src/backend/tagger.py`):
1. **Deterministic Slot Extraction**: High-precision regex extracts quantitative business metrics:
   - Payment terms: `net-30`, `net-45`, `net-60`, `net-90`
   - Availability SLOs: `uptime-99.9pct`, `uptime-99.95pct`, `uptime-99.99pct`
   - Liability caps: `cap-12mo`, `cap-fees-paid`
   - Structural section numbers: `sec-12`, `sec-4.2`
2. **Local LLM Semantic Tagging**: Local Ollama `qwen2.5-coder:7b` extracts 3–5 lowercase domain tags and a 1-sentence executive micro-digest.
3. **Ensemble Union**: Merges deterministic slot tags with LLM semantic tags, ensuring critical numbers are **never lost**.
4. **Deterministic Fallback**: If Ollama times out or the GPU node is saturated, the system uses extractive first-sentence digests and slot anchors with zero cloud leakage.

### 2. Schema Enrichment
* **`DealEvidence`** (`deal_evidence`): Populated with `tags` (JSON array of strings), `summary` (1-sentence digest), and `topic` (canonical commercial doctrine).
* **`CommercialClauseVector`** (`commercial_clause_vectors`): Enriched with `tags`, `summary`, and `topic`.
* **`Clause`** (`clauses`): Added `tags` and `summary`.

### 3. Dual-Path Retrieval & Exact Tag Boosting
When retrieving deal exhibits or searching operative agreements (`src/backend/rag.py`):
* **Dual Retrieval (`retrieve_deal_evidence`)**: Performs dense vector search (`bge-large`, 1024-dim) combined with BM25 lexical full-text ranking.
* **Exact Tag Boost**: Chunks containing tags matching the inquiry receive an immediate **+20% score boost** (`score * 1.20`), guaranteeing that explicit slot queries (e.g., `net-30` or `uptime-99.9pct`) rank at the top.
* **Topic & Tag Filtering (`retrieve_clauses`)**: Direct relational SQL filtering by `topic` and `tag` before ranking.

### 4. Faceted Exploration UI & REST Endpoints
* **Streamlit Tab 1 (Deal Evidence Explorer)**: Interactive evidence card gallery with tag filters, topic chips, and 1-sentence micro-digests.
* **Streamlit Tab 3 (Agreements & Clauses)**: Displays clause-level tags and summary badges alongside relational graph metadata.
* **Streamlit Tab 7 (Commercial Ops & DraftPro)**:
  - **Contract Portfolio**: Active vendor contracts, renewal countdown badges, and contract registration.
  - **Invoices & Receivables**: KPI summary (Total Receivables, Paid, Overdue), aging distribution, and invoice generation.
  - **OCR Document Extractor**: Upload invoice/contract scans for instant line-item and counterparty extraction.
  - **DraftPro Generator**: Rapid template-based commercial agreement generation with live markdown preview and export.
* **Core REST API**:
  - `GET /api/deals/{deal_id}/evidence`: Enriched deal exhibits with tags, summary, and topic.
  - `GET /api/deals/{deal_id}/evidence/tags`: Aggregate unique tag distribution with occurrence counts for faceted UI filtering.
  - `GET /api/clauses?topic=...&tag=...`: Clause search with topic and tag filtering.

### 5. Commercial Operations & DraftPro REST API (`/api/business`)
* `POST /api/business/contracts`: Register a vendor contract with renewal horizons and alert thresholds.
* `GET /api/business/contracts`: List all active vendor contracts.
* `GET /api/business/contracts/expiring`: Query contracts expiring within `days_ahead` (default 60).
* `GET /api/business/contracts/{id}`: Detailed vendor contract metadata.
* `PATCH /api/business/contracts/{id}`: Update terms, expiration dates, or status.
* `DELETE /api/business/contracts/{id}`: Delete contract record.
* `POST /api/business/invoices`: Issue a client invoice with calculated line items.
* `GET /api/business/invoices`: Enumerate invoices filtered by client or status.
* `GET /api/business/invoices/outstanding`: Real-time receivables total and aging breakdown.
* `PATCH /api/business/invoices/{id}/status`: Transition invoice status (`sent`, `paid`, `overdue`).
* `POST /api/business/ocr/parse`: Multipart file upload for heuristic document parsing.
* `GET /api/business/templates`: Enumerate available DraftPro commercial templates.
* `GET /api/business/templates/{template_id}/schema`: Query required/optional template fields.
* `POST /api/business/templates/generate`: Render formatted commercial contract.
* `POST /api/business/templates/revise`: Apply instruction-based revisions to commercial drafts.

---

## 🏗️ Architecture

```
                                ┌────────────────────────────────┐       ┌────────────────────────────────┐
                                │     KruschBiz Web Dashboard    │       │     IDE Agents / Subagents     │
                                │  (Streamlit / 127.0.0.1:8506)  │       │ (Claude / Antigravity / Wind)  │
                                │  *Executive Navy/Gold Styling* │       │  *6 Canonical Tools (~950 tok)*│
                                └──────────────┬─────────────────┘       └──────────────┬─────────────────┘
                                               │ REST (CORS Restricted)                 │ Stdio JSON-RPC
                                               │                         ┌──────────────▼─────────────────┐
                                               │                         │      KruschBiz MCP Server      │
                                               │                         │      (src/mcp/server.py)       │
                                               │                         └──────────────┬─────────────────┘
                                               │                                        │ In-process / RPC
                                ┌──────────────▼────────────────────────────────────────▼─┐
                                │                   KruschBiz Backend                     │
                                │              (FastAPI / 127.0.0.1:8086)                 │
                                │      *Relational Graph, Grounding & Commercial Ops*     │
                                └───┬──────────────────────┬──────────────────────────┬───┘
                                    │                      │                          │
                     SQL / pgvector │                      │ Nexus Spine / OCR        │ Local HTTP
                                    │                      │ Standalone               │
         ┌──────────────────────────▼───┐              ┌───▼───────────┐  ┌───────────▼──────────────┐
         │   PostgreSQL 16 + pgvector   │              │  Nexus Adapter│  │     Local Ollama Node    │
         │ (Contract Clauses & Evidence)│              │ Ingest Spine  │  │  ├─ bge-large (Embed)    │
         │        127.0.0.1:5436        │              │ (PDF/DOCX/MD) │  │  └─ qwen2.5:14b / 7b     │
         └──────────────────────────────┘              └───────────────┘  └──────────────────────────┘
```

---

## 💻 Hardware Requirements & Model Matrix

| Profile | Recommended Model | Minimum Hardware | Expected Speed | Suitable Use Case |
|---|---|---|---|---|
| **CPU / Lightweight** | `qwen2.5:7b` + `bge-large` | 16GB System RAM (8 threads) | ~10–18 tok/s | Air-gapped laptops, small office CPU nodes, rapid exploration |
| **GPU / Standard** | `qwen2.5:14b` + `bge-large` | 12GB+ VRAM (RTX 3060/4070, Apple Silicon 16GB+) | ~35–55 tok/s | High-precision commercial synthesis, SLA & liability risk spotting |
| **Workstation / Heavy** | `qwen2.5:32b` + `bge-large` | 24GB+ VRAM (RTX 3090/4090, Apple Silicon 36GB+) | ~20–30 tok/s | Complex M&A due diligence, multi-contract conflict analysis |

To configure models, update `.env`:
```env
OLLAMA_LLM_MODEL=qwen2.5:14b
OLLAMA_EMBED_MODEL=bge-large
```

---

## ⚡ Quickstart

### Prerequisites
* [Docker](https://docs.docker.com/get-docker/) & Docker Compose
* Local [Ollama](https://ollama.com/) instance:
  ```bash
  ollama pull bge-large
  ollama pull qwen2.5:14b
  ```

### 1. Clone & Configure
```bash
git clone https://github.com/kruschdev/krusch-biz.git
cd krusch-biz

cp .env.example .env
```

### 2. Launch Stack
```bash
docker compose up --build -d
```

Verify endpoints:
* **Frontend UI**: [http://localhost:8506](http://localhost:8506)
* **Backend API Docs**: [http://localhost:8086/docs](http://localhost:8086/docs)
* **Health & Diagnostics**: [http://localhost:8086/health](http://localhost:8086/health)

---

## 🔌 Model Context Protocol (MCP) Integration

## 🔌 Model Context Protocol (MCP) Integration

KruschBiz provides a native stdio JSON-RPC MCP server (`src/mcp/server.py`) exposing air-gapped corporate intelligence tools. To prevent prompt token bloat and routing indecision on local 7B/14B models, tools are consolidated into **6 high-leverage canonical tools** (~950 prompt tokens, reduced from ~3,500 tokens):

### Canonical 6-Tool Contract (Active Agent Surface)
| Canonical Tool | Action Verbs | Description |
|---|---|---|
| `contract_intelligence` | `search`, `get_clause`, `resolve_controlling`, `detect_conflicts`, `diff_instruments` | Unified query engine for hybrid vector+lexical search, clause inspection, controlling amendment resolution, and contract conflict detection. |
| `manage_deal` | `log`, `list`, `audit` | Securely log confidential transactions with embeddings, enumerate active deals, and retrieve proposition grounding audits. |
| `vendor_portfolio` | `register`, `list_expiring`, `list` | Track vendor master agreements, contract values, expiration countdowns, and renewal alert horizons. |
| `accounts_receivable` | `create`, `list`, `update_status` | Commercial client invoicing with automated server-side math, status lifecycle, and aging bucket breakdown (Current, 1–30d, 31–60d, 61–90d, 90d+). |
| `commercial_drafting` | `executive_brief`, `standard_template` | Draft executive deal memos with assertion grounding or generate standard contracts (NDA, MSA, SOW, ICA, Demand Letter) from verified DraftPro templates. |
| `document_pipeline` | `ingest`, `ocr_extract` | Ingest documents into the citation spine or run heuristic OCR to extract line items, amounts, dates, and counterparties. |

> [!TIP]
> **Complete Backwards Compatibility**: The MCP dispatcher internally retains routes for all 16 legacy micro-tools (`search_contracts_and_policies`, `get_clause_details`, `register_vendor_contract`, `create_business_invoice`, etc.), ensuring zero disruption to existing scripts or callers.

---

## 🧪 Automated Testing & CI Gates

```bash
# Run full unit, integration, tagger, business ops, OCR, template, and MCP test suite (100 tests)
pytest tests

# Run MCP server tests (verifies 6 canonical tools + 16 legacy aliases)
pytest tests/test_mcp.py

# Run commercial operations, OCR, and DraftPro test suites
pytest tests/test_business_ops.py tests/test_business_ocr.py tests/test_business_templates.py

# Run commercial tagger and deal evidence tests
pytest tests/test_commercial_tagger.py tests/test_deal_evidence.py

# Run 3-gate empirical evaluation harness
python scripts/eval_retrieval_and_grounding.py

# Run ruff code quality and lint gate
ruff check .
```

---

## 📊 Empirical Evaluation Scorecards

KruschBiz separates performance reporting into two distinct scorecards: the **Fixture Corpus (Bootstrap Baseline)** and the **Held-Out Redacted Contracts Gate** (real external agreements not present in training fixtures).

### Gate 1: Fixture Corpus Scorecard (Bootstrap Baseline)
*Evaluated against `data/eval/golden_business_eval.json` (25 seeded corporate test cases).*

| Metric | Target | Measured Score | Evaluation Notes |
|---|---|---|---|
| **Recall@1 (Top-1 Accuracy)** | > 80.0% | **84.0%** | Relevant governing clause returned as top hit |
| **Recall@5 (Top-5 Coverage)** | > 90.0% | **92.0%** | Gold section contained in top 5 retrieved items |
| **Mean Reciprocal Rank (MRR)** | > 0.850 | **0.873** | Harmonic mean of gold citation retrieval rank |
| **Distractor / Stale Agreement Leaks** | 0 | **0** | Expired 2021 MSA never outranked 2025 controlling agreement |
| **Average Query Latency** | < 250 ms | **123.4 ms** | Hybrid search + relational graph hydration |

### Gate 2: Unmocked Embedding Gate (Real `bge-large` 1024-d Vectors)
*Evaluated with real 1024-dimensional cosine similarity vectors frozen in `data/eval/embeddings/` (no live Ollama required in CI).*

| Metric | Measured Score | Evaluation Notes |
|---|---|---|
| **Pure Vector Recall@1** | **80.0%** | Dense cosine vector retrieval top-1 |
| **Pure Vector Recall@5** | **92.0%** | Dense cosine vector retrieval top-5 |
| **Pure Vector MRR** | **0.860** | Mean reciprocal rank across all query vectors |

### Gate 3: Held-Out Contracts Gate (Real Redacted Instruments)
*Evaluated against `data/eval/heldout_contracts.json` (12 held-out redacted commercial contracts with exact claim spans and numeric slots).*

| Metric | Target | Measured Score | Evaluation Notes |
|---|---|---|---|
| **Held-Out Recall@1** | > 70.0% | **75.0%** | Top-1 accuracy on unseen commercial agreements |
| **Held-Out Recall@5** | > 90.0% | **100.0%** | Top-5 coverage across held-out agreements |
| **Held-Out MRR** | > 0.800 | **0.875** | Mean reciprocal rank on held-out instruments |
| **Priority Inversions** | 0 | **0** | Superseded instrument never ranked above a controlling one |

### Grounding Calibration & Confusion Matrix
*Evaluated across discrete proposition claims using exact span overlap + structured slot assertion matching.*

| Category | Tested Propositions | Accurate Classifications | Accuracy Rate |
|---|---|---|---|
| **VERIFIED** | 12 | 12 | **100.0%** |
| **INVENTED_CLAUSE** | 12 | 12 | **100.0%** |
| **DIVERGENT_TERM** | 11 | 7 | **63.6%** |
| **SUPERSEDED_TERM** | 1 | 1 | **100.0%** |
| **Overall Calibration Accuracy** | 36 | 32 | **88.89%** |

---

## 📜 License

KruschBiz is open-source software licensed under the **[MIT License](LICENSE)**.
