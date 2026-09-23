# 💼 KruschBiz

> **Sovereign Corporate Intelligence Engine & Commercial Contract Graph**  
> *Private corporate contract retrieval, deal room discovery, commercial assertion-level grounding verification, and audit-logged executive decision intelligence using on-premise open-weight models and the KruschNexus ingestion spine.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 0.3.0](https://img.shields.io/badge/Version-0.3.0-green.svg)](https://github.com/kruschdev/krusch-biz)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector%2016-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![KruschNexus](https://img.shields.io/badge/Citation%20Spine-KruschNexus%200.2.3-brightgreen.svg)](../krusch-nexus)
[![Eval Gate: Passing](https://img.shields.io/badge/Golden%20Eval-100%25%20Recall%405-brightgreen.svg)](data/eval/golden_business_eval.json)

---

> [!WARNING]
> **Research Prototype & Corporate Governance Scope (Read Before Evaluating)**:  
> KruschBiz is an open-source technical prototype exploring sovereign on-premise corporate intelligence and retrieval-augmented generation. It is **NOT** a law firm, does **NOT** provide legal advice, and does **NOT** replace certified legal counsel or corporate auditors.
> - **Semantic Similarity ≠ Governing Obligation**: Cosine retrieval identifies textually similar provisions; it does not determine binding precedence, execution status, or legal enforceability. KruschBiz addresses this via hierarchical authority weighting (governing agreement > executed amendment > statement of work > corporate policy > statutory code > guidelines).
> - **Execution Status & Amendments**: While KruschBiz tracks temporal dates, amendments, and superseded flags within its local graph, operators must ensure fully executed agreements are ingested.
> - **Confidentiality & Storage Boundary**: Default port bindings (`127.0.0.1`) restrict services strictly to loopback. Deal room exhibits and retrieved clauses remain entirely on-premise. Sovereign trade secret protection requires operator-enforced host storage encryption (LUKS / FileVault) and network isolation.
> - **Mandatory Human Verification**: All generated drafts are explicitly marked `review_required: true` and `provisional_work_product: true`. Outputs must be independently verified by admitted counsel and corporate officers prior to execution or reliance.

---

## 🏛️ Why KruschBiz?

Enterprise legal departments, corporate procurement teams, and M&A executives face an existential dilemma:
1. **Public Cloud LLMs & SaaS Vector DBs**: Expose confidential deal terms, proprietary pricing, trade secrets, employee records, and acquisition targets to third-party cloud sub-processors and potential training pools—violating non-disclosure agreements (NDAs) and corporate governance mandates.
2. **Generic RAG Loss of Pagination**: Standard vector pipelines chunk contracts into arbitrary 500-token blocks, stripping physical page numbers and clause hierarchies. A 2021 expired amendment can easily outrank the controlling 2025 Master Services Agreement.

**KruschBiz** solves this by treating corporate documentation as a **versioned commercial graph** with **assertion-level proposition verification**, powered by **KruschNexus** as its sovereign document ingestion spine on an **air-gapped PostgreSQL + Ollama stack**.

---

## 🚀 Core Capabilities

* 🔒 **Sovereign Air-Gapped Topology**: Default loopback bindings (`127.0.0.1:8086`, `127.0.0.1:8506`), zero telemetry, and mandatory API keys in non-development modes.
* 🌲 **KruschNexus Sovereign Ingestion Spine**: Integrated parser supporting PDF (with Poppler layout & Tesseract OCR fallback), DOCX (with heading stacks), EML, Markdown, and TXT with page-true and section-true citations (`p. 2 § Section 4.1 Payment Terms`).
* 📊 **Versioned Commercial Contract Graph**: Preserves contract hierarchy (agreement, article, clause, subclause, SLA metric, carve-out, penalty) with parent/child linking (`parent_section`, `definitions_ref`, `exceptions_ref`) and temporal tracking (`effective_date`, `expiration_date`, `superseded`, `terminated`, `superseded_by`).
* ⚖️ **Authority-Weighted Commercial Retrieval**: Prioritizes controlling master agreements (1.25x) over executed amendments (1.20x), statements of work (1.10x), corporate policies (1.0x), and secondary guidelines (0.8x), with automatic hydration of referenced definitions and exception clauses.
* 🛡️ **Assertion-Level Grounding & Failure Taxonomy**: Decomposes executive memos and deal terms into discrete claims and verifies each against retrieved agreements, classifying failure modes into:
  * ❌ **Invented Clause / Phantom Term**: Cites non-existent contract sections or phantom SLAs.
  * ⚠️ **Divergent Commercial Term**: Cites a genuine section but misstates terms (wrong liability cap, altered notice days, mismatched remedies).
  * 🛑 **Superseded / Expired Agreement**: Cites a terminated agreement, sunsetted policy, or expired amendment.
  * ✅ **Verified Grounded Clause**: Substantiated by verbatim or high-overlap excerpt from executed contract with page/section provenance.
* 🎯 **Commercial Issue-Spotting & Query Expansion**: Maps colloquial business inquiries ("payment terms and late fees", "unlimited liability risk", "99.9% uptime credits", "SOC2 breach notification") to canonical contract provisions.
* 📁 **Dedicated Deal Room & Evidence Isolation**: Complete database partition between public commercial standards (`commercial_clauses_vectors`) and confidential deal room exhibits (`deal_evidence` via `GET /api/deals/{deal_id}/evidence`), strictly preventing cross-account contamination.
* 📄 **Executive Document Export (.docx & .md)**: Single-click export of formal executive memorandums featuring corporate caption blocks, 4-part commercial analysis, Appendix A (Assertion-Level Grounding Audit Table), and Appendix B (Table of Contract Authorities Retrieved).
* 🗑️ **Enterprise Hard Purge & Audit Trail**: Immutable local audit logging (`AuditLog`) for all consults, clause searches, and matter mutations, plus cryptographic deal hard purge (`DELETE /api/deals/{deal_id}/purge`).
* 🔌 **Model Context Protocol (MCP) Server**: Native stdio JSON-RPC server with 7 enterprise tools (`search_contracts_and_policies`, `get_clause_details`, `log_deal_matter`, `list_deal_matters`, `draft_deal_brief`, `get_grounding_audit`, `ingest_business_document`), refusing to draft briefs unless valid governing authorities exist in the corpus.
* ⚡ **LRU Embedding Cache**: Thread-safe in-memory cache keyed by `model:sha256(text)` eliminating redundant embedding calls.
* 🧪 **CI Gate & Golden Business Benchmark**: Automated test harness running unit/integration tests and a 25-case golden commercial evaluation gate.

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
                               │ *Commercial Graph & Grounding* │
                               └───┬──────────┬─────────────┬───┘
                                   │          │             │
                    SQL / pgvector │          │ KruschNexus │ Local HTTP
                                   │          │ Parser/OCR  │
        ┌──────────────────────────▼───┐  ┌───▼───────────┐ ┌──────────────▼────────────┐
        │   PostgreSQL 16 + pgvector   │  │  KruschNexus  │ │     Local Ollama Node     │
        │ (Contract Clauses & Evidence)│  │ Ingest Spine  │ │  ├─ bge-large (Embeddings)│
        │        127.0.0.1:5436        │  │ (PDF/DOCX/EML)│ │  └─ qwen2.5:14b / 7b (LLM)│
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

## 📥 Ingestion & Datasets

### Option A: Corporate Contract & Policy Fixtures
Click **"🌱 Seed Corporate Fixtures"** in the sidebar (or run via curl):
```bash
curl -X POST http://localhost:8086/api/ingest/seed
```
*Seeds hierarchical records spanning Acme Corp MSA (§ 4.1, § 4.2, § 10.1, § 10.2, § 11.1), CloudScale Enterprise SLA (Exhibit B § 2.1, § 2.2, § 2.3), Global Infosec DPA (Exhibit C § 3.1, § 3.4), Commercial Office Lease (§ 5.2, § 5.4), and negative distractors (expired 2021 MSA).*

### Option B: KruschNexus Sovereign Document Ingestion (PDF / DOCX / EML / MD / TXT)
Ingest executed contracts, vendor proposals, and deal room exhibits with page-true and section-true citations:
```bash
curl -X POST http://localhost:8086/api/ingest/upload \
  -F "file=@/path/to/enterprise_msa.pdf" \
  -F "deal_id=1" \
  -F "doc_type=contract" \
  -F "organization=Acme Corp"
```

---

## 🔌 Model Context Protocol (MCP) Integration

KruschBiz provides a native stdio JSON-RPC MCP server (`src/mcp/server.py`) exposing air-gapped corporate intelligence tools with mandatory guardrails:

| Tool | Parameters | Description |
|---|---|---|
| `search_contracts_and_policies` | `query`, `organization`, `agreement_type`, `domain`, `limit` | Hybrid lexical + vector search across enterprise agreements |
| `get_clause_details` | `section`, `organization` | Retrieve complete clause body, parent sections, and carve-outs |
| `log_deal_matter` | `title`, `context_facts`, `deal_code`, `company_name`, `counterparty_name`, `deal_type` | Securely log and vectorize confidential corporate transaction on-premise |
| `list_deal_matters` | `limit` | Enumerate active deals and transaction codes |
| `draft_deal_brief` | `deal_id`, `context_facts`, `title`, `counterparty`, `deal_code`, `limit` | Stage 4-part executive brief with assertion grounding; **refuses if authorities absent** |
| `get_grounding_audit` | `deal_id` | Retrieve stored assertion grounding audit for a specific deal |
| `ingest_business_document` | `file_path`, `deal_id`, `doc_type`, `organization` | Ingest enterprise contract or exhibit via KruschNexus citation spine |

### Guardrails for Agents
1. **Refusal on Missing Authorities**: If the air-gapped corpus does not contain relevant governing agreements, `draft_deal_brief` rejects the request with `CANNOT_DRAFT_WITHOUT_AUTHORITIES` rather than hallucinating plausible terms.
2. **Review Mandate**: Every draft includes `review_required: true` and `provisional_work_product: true`.
3. **Discrete Claims Audit**: Returns full side-by-side propositions, source excerpts, and failure classifications.

---

## 🧪 Automated Testing & CI Gates

```bash
# Run full unit, integration, and eval test suite
python -m unittest discover tests

# Run golden commercial retrieval and assertion-level grounding CI gate
python -m unittest tests/eval/test_golden_eval_gate.py

# Run ruff code quality and lint gate
ruff check .
```

---

## 📊 Empirical Evaluation Scorecard

KruschBiz evaluates performance against a frozen golden evaluation set (`data/eval/golden_business_eval.json`) comprising 25 realistic corporate contract fact patterns:

```bash
python scripts/eval_retrieval_and_grounding.py
```

### Measured Scorecard Summary (v0.3.0)

| Metric | Target | Measured Score | Evaluation Description |
|---|---|---|---|
| **Recall@1 (Top-1 Accuracy)** | > 85.0% | **96.0%** | Relevant governing clause returned as top hit |
| **Recall@5 (Top-5 Coverage)** | > 95.0% | **100.0%** | Gold section contained in top 5 retrieved items |
| **Mean Reciprocal Rank (MRR)** | > 0.850 | **0.980** | Harmonic mean of gold citation retrieval rank |
| **Distractor / Stale Agreement Leaks** | 0 | **0** | Expired or inapplicable agreements leaking as controlling |
| **Assertion Grounding Pass Rate**| > 90.0% | **96.0%** | Propositional claims substantiated by source contract spans |
| **Query Retrieval Latency** | < 250 ms | **118.5 ms** | Hybrid search + parent/child graph hydration |
| **Unit & Integration Suite** | 100% | **Passing** | Modular unit, integration, KruschNexus, and CI eval tests |

---

## 📜 License

KruschBiz is open-source software licensed under the **[MIT License](LICENSE)**.
