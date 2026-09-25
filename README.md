# 💼 KruschBiz

> **Confirmed-Edge Contract Precedence Graph & Slot Grounding Engine**  
> *Deterministic contract precedence resolution, typed DAG amendment traversal, and assertion-level slot grounding verification for corporate legal and deal intelligence.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 0.1.0-alpha.1](https://img.shields.io/badge/Version-0.1.0--alpha.1-blue.svg)](https://github.com/kruschdev/krusch-biz)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector%2016-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Tests: 188 Passing](https://img.shields.io/badge/Tests-188%20Passing-brightgreen.svg)](tests/)
[![CI Gates: 4/4 Passing](https://img.shields.io/badge/CI%20Gates-4%2F4%20Passing-brightgreen.svg)](scripts/eval_adversarial_corpus.py)

---

## 🎯 Product Boundary & Focus

**Billing, invoicing, and OCR live elsewhere.**

KruschBiz is built for one job:
1. **Determining the controlling contractual instrument and clause** across complex multi-document families, chronological amendment chains, and schedule carve-outs.
2. **Auditing and grounding generated commercial claims** against the controlling text using typed slot primitives and a canonical failure taxonomy.

Operational sludge (accounts receivable aging, OCR ingestion, invoice templates) has been permanently excised to sibling packages. Deep theoretical background on why standard vector search collapses on commercial agreements is detailed in [`docs/why_krusch_biz_differs_from_business_rag.md`](docs/why_krusch_biz_differs_from_business_rag.md). Comprehensive graph model and algorithm details are documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## ⚡ Core Architectural Invariants

* **Confirmed-Edge Invariant**: Relation extraction proposes edges with `status='proposed'`. The controlling document resolver walks **only confirmed edges** (`status='confirmed'`). Unconfirmed proposals never silently alter controlling terms and are returned strictly as advisories.
* **DAG Precedence Resolver**: Transitive DAG walk (`resolve_controlling_clause`) resolves multi-hop amendment chains (A → B → C) chronologically by effective date, with DFS recursion-stack cycle detection, self-loop prevention, and a depth cap (`depth < 32`).
* **Unexecuted Draft Isolation**: Agreements with `execution_status='draft'` cannot defeat, supersede, or amend executed agreements in precedence resolution (enforced on both `SUPERSEDES` and `AMENDS`).
* **Document Hierarchy Safeguards**: Master Agreements outrank SOWs/schedules on general governance (liability, indemnification, governing law); schedules outrank Master Agreements strictly on commercial parameters (fees, SLAs, deliverables).
* **Canonical Grounding Failure Codes**: Verification audits generated assertions against the exclusive authority set (controlling clause + amendment trail + incorporated clauses + carve-outs) and categorizes failures into:
  `WRONG_INSTRUMENT`, `SLOT_MISMATCH`, `UNIT_MISMATCH`, `NEGATED_OBLIGATION`, `PARTIAL_SUPPORT`, `SUPERSEDED`, `NO_AUTHORITY`, `UNCITED_NUMERIC_CLAIM`, and `UNGROUNDED_TOPIC`.
* **Closed Commercial Taxonomy & Slot Spans (v3)**: 16 canonical commercial topics (`PAYMENT_TERMS`, `LIABILITY_CAP`, `CHANGE_OF_CONTROL`, `ASSIGNMENT`, `NOTICES`, etc.) with quantitative, multi-currency (USD, EUR, GBP), and typed polarity slots extracted with exact character offset spans (`slot_spans`) and a frozen 32-character `clause_uid` hash.
* **Air-Gapped Sovereign Security**: Loopback-bound (`127.0.0.1:8086`, `127.0.0.1:8506`), boot-check failure on non-loopback or placeholder API keys outside development, single `tenant_id:key_secret` auth story rejecting header spoofing (HTTP 403), and pre-spool MIME magic-byte validation rejecting executable binaries (`MZ`, `\x7fELF`, Mach-O) and HTML-disguised PDFs.
* **Transactional Purge & Append-Only Audit**: Atomically cleans deal and agreement records with zero orphan rows across all tables. Audit log records reject `UPDATE` and `DELETE` at the database engine level via SQLAlchemy event listeners.
* **Dual MCP Architecture**:
  * **Canonical Domain MCP** (`src/mcp/server.py`): Exactly **4 high-leverage tools** (`contract_intelligence`, `manage_deal`, `ingest_contract`, `verify_grounding`).
  * **Sovereign Gateway MCP** (`src/mcp/gateway.py`): Exactly **5 cross-domain verbs** (`ask_law`, `ask_biz`, `check_compliance`, `ingest`, `purge`) strictly constrained to <450 prompt tokens (~428 tokens).

---

## 📊 Empirical Evaluation & CI Scorecard

Evaluation results are tracked and regenerated by CI in [`data/eval/scorecard.json`](data/eval/scorecard.json):

| Evaluation Gate | Dataset / Scope | Primary Metric | Target | Result |
|---|---|---|---|---|
| **Gate 1: Synthetic Smoke** | Smoke test fixtures (N=25) | Recall@5 | ≥ 85.0% | **92.0%** (MRR 0.853) |
| **Gate 2: Unmocked Embedding** | Deterministic `bge-large` vectors (N=25) | Pure Vector Recall@5 | ≥ 90.0% | **92.0%** (MRR 0.860) |
| **Gate 3: Held-Out Contracts** | Redacted real-world agreements (N=12) | Held-Out Recall@5 | ≥ 95.0% | **100.0%** (MRR 0.958) |
| | | Superseded Inversions | 0 inversions | **0 inversions** |
| **Gate 4: Calibration Matrix** | Grounding assertions (N=48) | Macro F1 | ≥ 75.0% | **96.41%** (Acc 91.67%) |
| **Adversarial Multi-Doc Pack** | 7 complex multi-document families | Relation F1 | ≥ 85.0% | **100.0%** |
| | (Silent overrides, carve-outs, side letters) | Controlling Clause Acc | ≥ 95.0% | **100.0%** (13/13) |
| | | Proposition Grounding | ≥ 95.0% | **100.0%** (28/28) |
| **The Ugly Real Pack** | Real-world 7-instrument stress test | Temporal Matrix | 6/6 phases | **6/6 passed** |
| | (Stale MSA + Restated MSA + 3 Amds + Draft Amd + SOW Fee) | | | |

---

## ⚖️ Scope & Compliance Disclaimer

> **KruschBiz is not a compliance product.**
>
> Full statutory compliance, regulatory precedence, and legislative analysis live in sibling packages ([`krusch-law`](../krusch-law) and [`krusch-bizlaw`](../krusch-bizlaw)). The demo ruleset in [`mandates/ca_demo.yaml`](mandates/ca_demo.yaml) is provided strictly as a technical demonstration of cross-domain join mechanics. Queries specifying jurisdictions other than California return `UNSUPPORTED_JURISDICTION` with an advisory pointing to `krusch-bizlaw`.
>
> KruschBiz outputs are provisional technical analysis and do **NOT** constitute legal advice.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.11 or 3.12
- Local Ollama instance with `bge-large` (embeddings) and `qwen2.5-coder:7b` (tagger/LLM)
- SQLite (local development) or PostgreSQL 16 + pgvector (production)

### 1. Installation
```bash
git clone https://github.com/kruschdev/krusch-biz.git
cd krusch-biz
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure Environment
```bash
cp .env.example .env
# Default settings bind strictly to loopback (127.0.0.1)
```

### 3. Run Test Suite
```bash
pytest tests -v
```

### 4. Launch Services
```bash
# Terminal 1: Backend REST API (Port 8086)
uvicorn src.backend.main:app --host 127.0.0.1 --port 8086 --reload

# Terminal 2: Streamlit Review UI (Port 8506)
streamlit run src/frontend/app.py --server.port 8506 --server.address 127.0.0.1

# Terminal 3: Canonical Domain MCP Server (Stdio)
python -m src.mcp.server
```

---

## 📚 Documentation Directory

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): Formal graph specification, data schemas, resolver rules, clause UID hashing, and security controls.
- [`docs/why_krusch_biz_differs_from_business_rag.md`](docs/why_krusch_biz_differs_from_business_rag.md): Deep-dive white paper on the failure modes of generic vector RAG in commercial contracting.
- [`docs/ORCHESTRATOR_SPEC.md`](docs/ORCHESTRATOR_SPEC.md): Cross-domain orchestrator specification between KruschBiz and KruschLaw.
- [`mandates/ca_demo.yaml`](mandates/ca_demo.yaml): Demonstration statutory join ruleset with California jurisdiction scoping.
