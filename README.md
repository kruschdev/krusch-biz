# 💼 KruschBiz

> **Sovereign Corporate Intelligence Engine & Commercial Contract Graph**  
> *Private corporate contract retrieval, relational contract graph walking, commercial assertion-level grounding verification, and audit-logged executive decision intelligence using on-premise open-weight models and the sovereign KruschNexus ingestion spine.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 0.2.0](https://img.shields.io/badge/Version-0.2.0-green.svg)](https://github.com/kruschdev/krusch-biz)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector%2016-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Tests: 129 Passing](https://img.shields.io/badge/Tests-129%20Passing-brightgreen.svg)](tests/)
[![CI Gates: Passing](https://img.shields.io/badge/CI%20Gates-4%2F4%20Passing-brightgreen.svg)](scripts/eval_retrieval_and_grounding.py)

---

> [!WARNING]
> **Research Prototype & Corporate Governance Scope (Read Before Evaluating)**:  
> KruschBiz is an open-source technical prototype exploring sovereign on-premise corporate intelligence and retrieval-augmented generation. It is **NOT** a law firm, does **NOT** provide legal advice, and does **NOT** replace certified legal counsel or corporate auditors.
> - **Semantic Similarity ≠ Governing Obligation**: Cosine retrieval identifies textually similar provisions; it does not determine binding precedence, execution status, or legal enforceability. KruschBiz resolves this via explicit graph edges (`AMENDS`, `SUPERSEDES`, `INCORPORATES`, `SCHEDULE_OF`, `CARVES_OUT`) and a recursive controlling-document resolver.
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
- **Controlling Document Resolver**: Recursive graph-walking algorithm with cycle detection and typed precedence that determines controlling instruments and clauses given `(counterparty, topic, as_of_date)`.
- **Closed Taxonomy & Structured Slot Extraction**: Extracts canonical commercial slots (`net_days`, `late_interest_pct`, `uptime_pct`, `cap_period_months`, `payment_notice_days`, `breach_notice_days`, `termination_notice_days`) with exact character offset spans (`slot_spans`) directly into JSON columns at ingest.
- **Assertion-Level Proposition Grounding Scanner**: Verifies generated claims using citation existence in controlling sets, normalized slot primitives, currency/basis checks, negation/carve-out guards, and token span containment.
- **Air-Gapped Sovereign Ingestion Spine**: Standalone parser and chunker with pre-spool file magic bytes validation and chunk DOS limits.

---

## 🚀 Core Capabilities

* 🔒 **Sovereign Air-Gapped Topology**: Default loopback bindings (`127.0.0.1:8086`, `127.0.0.1:8506`), code-level loopback verification, zero external telemetry, and mandatory tenant-bound API keys outside dev.
* 🕸️ **Relational Contract Graph & Controlling Resolver**:
  * Explicit database models: `agreements`, `clauses`, and `agreement_relations`.
  * Candidate relation extractor (`src/backend/relations.py`) scans text for amendment clauses, emitting proposed relations for human review.
  * Transitive DAG walk (`resolve_controlling_clause`) resolves amendment chains (A → B → C) with cycle detection (`max_depth=32`) and a typed precedence table (`SUPERSEDES`, `AMENDS`, `SCHEDULE_OF`, `CARVES_OUT`, `INCORPORATES`).
  * Emits an authoritative `amendment_trail` audit artifact and dynamic confidence score.
  * `detect_contract_conflicts(counterparty, as_of_date)` surfaces diverging terms across live operative agreements before LLM synthesis.
  * Stable clause identity (`clause_uid`) hashed from `(instrument_family, canonical_topic, slot_signature)`.
* 🎯 **Closed Commercial Taxonomy & Open Structured Slots**:
  * 13 canonical commercial topics (`PAYMENT_TERMS`, `LATE_FEE`, `LIABILITY_CAP`, `LIABILITY_CARVE_OUT`, `INDEMNITY`, `SLA_UPTIME`, `SLA_CREDIT`, `DATA_PROTECTION`, `BREACH_NOTIFICATION`, `AUDIT_RIGHTS`, `TERMINATION_CONVENIENCE`, `MOST_FAVORED_NATION`, `GOVERNING_LAW`).
  * Structured slot extraction into JSON columns at ingest with character offset provenance spans (`slot_spans`).
* 🛡️ **Layered Assertion Grounding & Failure Taxonomy**:
  * Multi-tier verification pipeline (`src/backend/rag.py`):
    1. **Citation Resolve**: Cited instrument and section must exist in the *retrieved controlling set*, rejecting `WRONG_INSTRUMENT`.
    2. **Slot Value Normalization**: Type-safe comparison of normalized slot primitives (`30` vs `30.0` vs `"Net 30"` vs `"thirty (30)"`).
    3. **Numerical Unit & Basis Verification**: Catches currency mismatches (€ vs $) and interest frequency divergence (monthly vs APR).
    4. **Negation & Carve-Out Guard**: Catches dropped exceptions (e.g. asserting uncapped liability or dropping Gross Negligence carve-outs) as `NEGATED_OBLIGATION`.
    5. **Partial Support Detection**: Emits `PARTIAL_SUPPORT` when topic matches but numerical values are unsubstantiated.
    6. **Token Span Containment**: Substantive token containment rather than loose bag-of-words overlap.
* 🛑 **Agent Refusal Guardrails**:
  * `CANNOT_DRAFT_WITHOUT_AUTHORITIES`: Refuses drafting when zero relevant authorities exist in the graph.
  * `REFUSAL_ALL_AUTHORITIES_SUPERSEDED`: Refuses drafting if all retrieved authorities are superseded or terminated.
  * `CANNOT_DRAFT_EMBEDDINGS_UNAVAILABLE`: Strictly refuses drafting on constant mock vectors if embeddings are offline.
* 🌲 **Sovereign Document Ingestion**:
  * Pre-spool magic byte verification (`%PDF-`, `PK\x03\x04`, `\xd0\xcf\x11\xe0`) rejecting executable binaries (`MZ`, `\x7fELF`) before disk spooling.
  * Standalone parser adapter supporting PDF, DOCX, TXT, MD, CSV with natural legal boundary chunking.
  * Max chunk DOS guardrail (`MAX_INGEST_CHUNKS_PER_DOC = 500`).
  * Transactional `IngestJob` state machine (`queued → parsing → extracting_slots → embedding → indexed | failed`).
* 🏢 **Multi-Tenant Isolation**: Key-bound tenant authentication (`tenant_id:key_secret`) strictly rejecting `X-Tenant-ID` header spoofing (HTTP 403).
* 🧪 **Quarantined Commercial Operations (Labs Module)**:
  * Non-core operations (`invoicing`, `AR aging`, heuristic invoice extraction, and DraftPro templates) are quarantined under `src/labs/` and feature-gated behind `ENABLE_BUSINESS_OPS=true` to ensure the core contract graph, retrieval engine, and grounding scanner remain strictly focused.
* 🏷️ **Commercial Ensemble Chunk Tagging & Micro-Digests**: Integrated commercial chunk tagger (`src.backend.tagger`) performing an ensemble merge of deterministic contractual slot tags (`net-30`, `uptime-99.9pct`, `cap-12mo`, `sec-12`) with local Ollama (`qwen2.5-coder:7b`) with LRU caching, JSON repair, and slot priority.
* 🔍 **Unified Commercial Retrieval Scorer**: Single Python scorer across SQLite and Postgres combining dense vector cosine similarity with lexical BM25 cover density, tag boosts, and a structural `superseded_penalty` ensuring controlling clauses always outrank superseded terms.
* 🗑️ **Atomic Purge & Immutable Audit Trail**:
  * Multi-table transactional purge (`purge_agreement_transactional`, `purge_deal_matter_transactional`) eliminates orphan records in a single database transaction with typed deal code confirmation.
  * Append-only immutable `AuditLog` enforced by database event listeners rejecting updates and deletions.
* 🔌 **Focused Model Context Protocol (MCP) Server**: Exposes 4 high-leverage canonical tools (`contract_intelligence`, `manage_deal`, `ingest_contract`, `verify_grounding`) over stdio JSON-RPC without prompt bloat or confusing legacy tool sprawl.


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

KruschBiz provides a native stdio JSON-RPC MCP server (`src/mcp/server.py`) exposing sovereign corporate intelligence tools. To prevent prompt token bloat and routing confusion on local 7B/14B models, tools are strictly focused on **4 high-leverage canonical tools** (~700 prompt tokens, eliminating legacy tool sprawl):

### Canonical 4-Tool Contract (Active Agent Surface)
| Canonical Tool | Action Verbs | Description |
|---|---|---|
| `contract_intelligence` | `search`, `get_clause`, `resolve_controlling`, `detect_conflicts`, `diff_instruments` | Unified query engine for hybrid vector+lexical search, clause inspection, controlling amendment DAG resolution, contract conflict detection, and side-by-side diffing. |
| `manage_deal` | `log`, `list`, `audit`, `draft_brief` | Securely log confidential transactions with embeddings, enumerate active deals, retrieve proposition grounding audits, and draft memos. |
| `ingest_contract` | `ingest_file` | Ingest enterprise documents into the sovereign citation spine with MIME magic byte verification and natural legal boundary chunking. |
| `verify_grounding` | `verify_claims` | Run assertion-level proposition grounding verification against governing contract authorities, returning a 6-way failure taxonomy. |

---

## 🧪 Automated Testing & CI Gates

```bash
# Run full unit, integration, tagger, security, adversarial grounding, and MCP test suite (129 tests)
pytest tests

# Run MCP server tests (verifies 4 canonical tools)
pytest tests/test_mcp.py

# Run adversarial grounding test suite (16 adversarial cases)
pytest tests/test_adversarial_grounding.py

# Run security hardening tests (tenant binding, rate limiting, magic bytes, constant vector refusal)
pytest tests/test_security_hardening.py

# Run multi-gate empirical evaluation harness (publishes raw scorecard JSON to data/eval/scorecard.json)
python scripts/eval_retrieval_and_grounding.py
```

---

## 📊 Empirical Evaluation Scorecards

KruschBiz evaluates retrieval and grounding through a multi-gate calibration harness (`scripts/eval_retrieval_and_grounding.py`). Gate 1 serves strictly as a **bootstrap smoke test**, while Gate 3 (Held-Out Redacted Contracts) represents the **primary evaluation gate** on external instruments not present in test fixtures.

### Gate 1: Fixture Corpus (Bootstrap Smoke Test)
*Evaluated against `data/eval/golden_business_eval.json` (25 seeded corporate test cases).*

| Metric | Target | Measured Score | Evaluation Notes |
|---|---|---|---|
| **Recall@1 (Top-1 Accuracy)** | > 75.0% | **80.0%** | Relevant governing clause returned as top hit |
| **Recall@5 (Top-5 Coverage)** | > 90.0% | **92.0%** | Gold section contained in top 5 retrieved items |
| **Mean Reciprocal Rank (MRR)** | > 0.800 | **0.853** | Harmonic mean of gold citation retrieval rank |
| **Distractor / Stale Agreement Leaks** | 0 | **0** | Expired 2021 MSA never outranked 2025 controlling agreement |
| **Average Query Latency** | < 250 ms | **123.8 ms** | Hybrid search + relational graph hydration |

### Gate 2: Unmocked Embedding Gate (Real `bge-large` 1024-d Vectors)
*Evaluated with real 1024-dimensional cosine similarity vectors frozen in `data/eval/embeddings/` (no live Ollama required in CI).*

| Metric | Measured Score | Evaluation Notes |
|---|---|---|
| **Pure Vector Recall@1** | **80.0%** | Dense cosine vector retrieval top-1 |
| **Pure Vector Recall@5** | **92.0%** | Dense cosine vector retrieval top-5 |
| **Pure Vector MRR** | **0.860** | Mean reciprocal rank across all query vectors |

### Gate 3: Held-Out Contracts Gate (Primary Held-Out Evaluation)
*Evaluated against `data/eval/heldout_contracts.json` (12 held-out redacted commercial contracts with exact claim spans and numeric slots).*

| Metric | Target | Measured Score | Evaluation Notes |
|---|---|---|---|
| **Held-Out Recall@1** | > 85.0% | **91.67%** | Top-1 accuracy on unseen commercial agreements |
| **Held-Out Recall@5** | > 95.0% | **100.0%** | Top-5 coverage across held-out agreements |
| **Held-Out MRR** | > 0.900 | **0.958** | Mean reciprocal rank on held-out instruments |
| **Priority Inversions** | 0 | **0** | Superseded instrument never ranked above a controlling one |
| **Superseded-in-Top-1 Rate** | 0.0% | **0.0%** | Zero superseded clauses mistakenly placed at Rank 1 |

### Grounding Calibration & Confusion Matrix
*Evaluated across discrete proposition claims using exact span containment, normalized slot primitives, currency/frequency basis verification, and carve-out guards.*

| Category | Tested Propositions | Accurate Classifications | Accuracy Rate | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| **VERIFIED** | 12 | 11 | **91.7%** | **100.0%** | **91.7%** | **95.7%** |
| **INVENTED_CLAUSE** | 12 | 12 | **100.0%** | **100.0%** | **100.0%** | **100.0%** |
| **DIVERGENT_TERM** | 11 | 9 | **81.8%** | **100.0%** | **81.8%** | **90.0%** |
| **SUPERSEDED_TERM** | 1 | 1 | **100.0%** | **100.0%** | **100.0%** | **100.0%** |
| **Macro Average** | **36** | **33** | **91.67%** | **100.0%** | **93.4%** | **96.4%** |

> [!NOTE]
> All evaluation runs generate an authentic, verifiable JSON scorecard published to [`data/eval/scorecard.json`](data/eval/scorecard.json).


---

## 📜 License

KruschBiz is open-source software licensed under the **[MIT License](LICENSE)**.
