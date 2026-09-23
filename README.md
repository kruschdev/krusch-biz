# 💼 KruschBiz

> **Sovereign Corporate Intelligence Engine & Commercial Contract Graph**  
> *Private corporate contract retrieval, relational contract graph walking, commercial assertion-level grounding verification, and audit-logged executive decision intelligence using on-premise open-weight models and the sovereign KruschNexus ingestion spine.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-green.svg)](https://github.com/kruschdev/krusch-biz)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector%2016-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
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
* 🗑️ **Hard Delete & Regulatory Audit Trail**:
  * `DELETE /api/deals/{deal_id}/hard-delete` permanently purges deals, exhibits, and grounding reports while logging an immutable regulatory audit entry.
* 🔌 **Model Context Protocol (MCP) Server**: Exposes 9 tools over stdio JSON-RPC for Claude Desktop, Antigravity, and autonomous agent workflows.

---

## 🏗️ Architecture

```
                               ┌────────────────────────────────┐
                               │     KruschBiz Web Dashboard    │
                               │  (Streamlit / 127.0.0.1:8506)  │
                               │  *Executive Navy/Gold Styling* │
                               └──────────────┬─────────────────┘
                                              │ REST (CORS Restricted)
                               ┌──────────────▼─────────────────┐
                               │       KruschBiz Backend        │
                               │   (FastAPI / 127.0.0.1:8086)   │
                               │ *Relational Graph & Grounding* │
                               └───┬──────────┬─────────────┬───┘
                                   │          │             │
                    SQL / pgvector │          │ Nexus Spine │ Local HTTP
                                   │          │ Standalone  │
        ┌──────────────────────────▼───┐  ┌───▼───────────┐ ┌──────────────▼────────────┐
        │   PostgreSQL 16 + pgvector   │  │  Nexus Adapter│ │     Local Ollama Node     │
        │ (Contract Clauses & Evidence)│  │ Ingest Spine  │ │  ├─ bge-large (Embeddings)│
        │        127.0.0.1:5436        │  │ (PDF/DOCX/MD) │ │  └─ qwen2.5:14b / 7b (LLM)│
        └──────────────────────────────┘  └───────────────┘ └───────────────────────────┘
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

KruschBiz provides a native stdio JSON-RPC MCP server (`src/mcp/server.py`) exposing air-gapped corporate intelligence tools with mandatory guardrails:

| Tool | Parameters | Description |
|---|---|---|
| `search_contracts_and_policies` | `query`, `organization`, `agreement_type`, `domain`, `limit` | Hybrid lexical + vector search across enterprise agreements |
| `get_clause_details` | `section`, `organization` | Retrieve complete clause body, parent sections, and carve-outs |
| `resolve_controlling_clause` | `counterparty`, `topic`, `as_of_date` | Walk amendment graph to resolve controlling operative clause |
| `detect_contract_conflicts` | `counterparty`, `as_of_date` | Scan for conflicting operational terms across live agreements |
| `log_deal_matter` | `title`, `context_facts`, `deal_code`, `company_name`, `counterparty_name`, `deal_type` | Securely log and vectorize confidential corporate transaction on-premise |
| `list_deal_matters` | `limit` | Enumerate active deals and transaction codes |
| `draft_deal_brief` | `deal_id`, `context_facts`, `title`, `counterparty`, `deal_code`, `limit` | Stage 4-part executive brief with assertion grounding; **refuses if authorities absent or superseded** |
| `get_grounding_audit` | `deal_id` | Retrieve stored assertion grounding audit for a specific deal |
| `ingest_business_document` | `file_path`, `deal_id`, `doc_type`, `organization` | Ingest enterprise contract or exhibit via citation spine |

---

## 🧪 Automated Testing & CI Gates

```bash
# Run full unit, integration, resolver, and security test suite (53 tests)
python -m unittest discover tests

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
