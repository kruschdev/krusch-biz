# 💼 KruschBiz

> **Sovereign Corporate Intelligence Engine & Commercial Contract Graph**  
> *Private corporate contract retrieval, relational contract graph walking, commercial assertion-level grounding verification, and audit-logged executive decision intelligence using on-premise open-weight models and the sovereign KruschNexus ingestion spine.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 0.1.0-alpha.1](https://img.shields.io/badge/Version-0.1.0--alpha.1-blue.svg)](https://github.com/kruschdev/krusch-biz)
[![Python 3.11 | 3.12](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.31+-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io)
[![pgvector](https://img.shields.io/badge/PostgreSQL-pgvector%2016-336791.svg?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Tests: 162 Passing](https://img.shields.io/badge/Tests-162%20Passing-brightgreen.svg)](tests/)
[![CI Gates: 4/4 Passing](https://img.shields.io/badge/CI%20Gates-4%2F4%20Passing-brightgreen.svg)](scripts/eval_adversarial_corpus.py)

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
* 🕸️ **Confirmed-Edge Precedence Graph & Controlling Resolver**:
  * Explicit database models: `agreements`, `clauses`, and `agreement_relations`.
  * **Human-Confirmed Edges Only for Precedence**: Candidate relation extractor (`src/backend/relations.py`) emits relations with `status='proposed'` for review. The controlling DAG resolver (`src/backend/resolver.py`) walks **only confirmed edges** (`status='confirmed'|'accepted'`); unconfirmed proposals never silently dictate terms and are returned as advisories.
  * **Unexecuted Draft Isolation**: Agreements with `execution_status='draft'` cannot defeat, supersede, or amend executed agreements.
  * **Document Hierarchy Safeguards**: Master Agreements outrank SOWs/schedules on general governance provisions; schedules outrank Master Agreements strictly on commercial parameters (fees, SLAs).
  * **Full Resolution Trace Auditing**: Every consult query persists an immutable [`ResolutionTraceRecord`](src/backend/db.py) recording traversed candidate paths, hops evaluated, and discard reasons.
  * Transitive DAG walk (`resolve_controlling_clause`) resolves multi-hop amendment chains (A → B → C) with cycle detection (`max_depth=32`) and typed precedence (`SUPERSEDES`, `AMENDS`, `SCHEDULE_OF`, `CARVES_OUT`, `INCORPORATES`).
  * Emits an authoritative `amendment_trail` audit artifact and dynamic confidence score.
  * `detect_contract_conflicts(counterparty, as_of_date)` surfaces diverging terms across live operative agreements before LLM synthesis.
  * Stable clause identity (`clause_uid`) hashed from `(instrument_family, canonical_topic, slot_signature)`.
* ⚖️ **The Join: Contract vs. Statute Compliance Engine**:
  * `POST /conflicts/contract-vs-statute` (and `/api/conflicts/contract-vs-statute`) links controlling corporate contract clause slots directly against statutory floors and ceilings.
  * Deterministic rule-based evaluation (no LLM hallucinations): compares contractual provisions against statutory ceilings (e.g., California AB 12 1-month security deposit limit effective 2024-07-01 under Cal. Civ. Code § 1950.5(c)(1)) and statutory floors (e.g., California 24-hour landlord entry notice under Cal. Civ. Code § 1954(a)).
  * Supports jurisdiction routing (`CA:Oakland`), temporal as-of dates, and surfaces structured compliance findings with exact statutory citations and coverage gap indicators.
* 📋 **One-Page Orchestrator Specification**:
  * Governed by [`docs/ORCHESTRATOR_SPEC.md`](docs/ORCHESTRATOR_SPEC.md): standardizes the `matter_ref` ↔ `deal_ref` entity mapping table, shared `as_of_date` query contracts, and 5 non-negotiable DO-NOT invariants across KruschBiz and KruschLaw.
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
* 🏢 **Multi-Tenant Isolation**: Key-bound tenant authentication (`tenant_id:key_secret`) strictly rejecting `X-Tenant-ID` header spoofing (HTTP 403) and cross-tenant IDOR access (HTTP 404).
* ✂️ **Excised Commercial Ops & Pure Precedence Focus**:
  * Non-core operations (invoicing, accounts receivable aging, heuristic OCR, and DraftPro templates) have been permanently excised from the default engine to guarantee zero bloat, strict latency boundaries, and an uncompromising focus on relational contract precedence, graph walking, and proposition grounding.
* 🏷️ **Commercial Ensemble Chunk Tagging & Micro-Digests**: Integrated commercial chunk tagger (`src.backend.tagger`) performing an ensemble merge of deterministic contractual slot tags (`net-30`, `uptime-99.9pct`, `cap-12mo`, `sec-12`) with local Ollama (`qwen2.5-coder:7b`) with LRU caching, JSON repair, and slot priority.
* 🔍 **Unified Commercial Retrieval Scorer**: Single Python scorer across SQLite and Postgres combining dense vector cosine similarity with lexical BM25 cover density, tag boosts, and a structural `superseded_penalty` ensuring controlling clauses always outrank superseded terms.
* 🗑️ **Atomic Purge & Immutable Audit Trail**:
  * Multi-table transactional purge (`purge_agreement_transactional`, `purge_deal_matter_transactional`) eliminates orphan records in a single database transaction with typed deal code confirmation.
  * Append-only immutable `AuditLog` enforced by database event listeners rejecting updates and deletions.
* 🔌 **Dual MCP Architecture (Canonical Domain Server + Sovereign Gateway Router)**:
  * **Domain MCP Server** (`src/mcp/server.py`): Exposes 4 high-leverage canonical tools (`contract_intelligence`, `manage_deal`, `ingest_contract`, `verify_grounding`) over stdio JSON-RPC without prompt bloat or legacy tool sprawl.
  * **Sovereign Gateway MCP Router** (`src/mcp/gateway.py`): Exposes a consolidated single 5-verb cross-repo gateway (`ask_law`, `ask_biz`, `check_compliance`, `ingest`, `purge`) strictly constrained to **<450 prompt tokens** (1,715 chars, ~428 tokens) for local 7B/14B models without context bloat.


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

### 4. 4-Tab Core Application Architecture
* **Tab 1: 🏛️ The Deal Room**:
  - Operational transaction summary, deal matters, and counterparty portfolio overview.
  - Automated controlling clause consult, citation verification, and proposition grounding audits.
  - **Prominent Uncertainty Alert Banner**: When unconfirmed proposed relation edges exist in the deal room, displays an amber `> ⚠️ CONTROLLING CLAUSE UNCERTAIN; N proposed relation link(s) pending human review.` alert across briefs and consultations.
* **Tab 2: 🔗 Relation Review Queue & Precedence Graph (The Core Product)**:
  - **First-Class Human-in-the-Loop Review Queue**: Evaluates proposed `AMENDS`, `SUPERSEDES`, `INCORPORATES`, and `CARVES_OUT` edges extracted from body-level restatements, conflict clauses, and schedules.
  - Displays triggering textual spans, algorithmic confidence, and provides one-click Accept, Reject, and Edit actions.
  - Interactive DAG visualization and instrument side-by-side diffing.
* **Tab 3: 🌲 Sovereign Ingest & Deep Extraction**:
  - Sovereign document ingestion with pre-spool MIME magic bytes validation (`%PDF-`, `PK\x03\x04`, `\xd0\xcf\x11\xe0`).
  - 7-step deterministic parsing and legal boundary chunking pipeline.
  - Structured commercial slot extraction (`net_days`, `uptime_pct`, `liability_cap`, `late_interest_pct`) with character offset provenance spans (`slot_spans`).
* **Tab 4: 🛡️ Adversarial Multi-Document Scorecard**:
  - Empirical verification dashboard benchmarked against 7 adversarial multi-document contract families.
  - Displays live scores across the 4 uncoupled metrics: Relation F1, Controlling Clause As-Of Accuracy, Slot Exact-Match, and Proposition Grounding.
  - One-click benchmark trigger calling `GET /api/evaluation/adversarial`.

### 5. Core REST API & Relation Management
* `GET /api/deals`: List active deal rooms and transaction portfolios.
* `GET /api/deals/{deal_id}/evidence`: Enriched deal exhibits with tags, summary, and canonical topics.
* `GET /api/clauses`: Clause search with topic, tag, and as-of date temporal filtering.
* `POST /api/consult`: Transitive precedence DAG walk determining controlling clauses for `(counterparty, topic, as_of_date)`.
* `POST /api/resolver/what-controls-export`: Generate comprehensive 1-page "What Controls as of DATE" GC legal memo and audit artifact across commercial topics.
* `POST /api/verify`: Assertion-level proposition grounding scanner returning a 6-way verification taxonomy.
* `GET /api/relations`: Query relation edges filtered by status (`proposed`, `confirmed`, `rejected`) and agreement.
* `PATCH /api/relations/{relation_id}`: Human-in-the-loop review endpoint to confirm, reject, or edit proposed relation types, scopes, and dates.
* `DELETE /api/relations/{relation_id}`: Delete an erroneous relation edge.
* `POST /api/conflicts/contract-vs-statute`: The Join: evaluate contractual slots against statutory floors and ceilings.
* `GET /api/evaluation/adversarial`: Retrieve the live 4-metric adversarial scorecard across 7 multi-document families.

---

## 🏗️ Architecture

```
                                ┌────────────────────────────────┐       ┌────────────────────────────────┐
                                │     KruschBiz Web Dashboard    │       │     IDE Agents / Subagents     │
                                │  (Streamlit / 127.0.0.1:8506)  │       │ (Claude / Antigravity / Wind)  │
                                │  *Executive Navy/Gold Styling* │       │  *4 Canonical Tools (~650 tok)*│
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
                                │         *Relational Graph, Resolver & Grounding*        │
                                └───┬──────────────────────┬──────────────────────────┬───┘
                                    │                      │                          │
                     SQL / pgvector │                      │ Nexus Spine / Ingest     │ Local HTTP
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

### 🌐 Sovereign Gateway MCP Router (<450 Prompt Tokens)

For cross-domain fleet coordination without prompt context bloat, KruschBiz also provides the hyper-compact 5-verb Gateway MCP router (`src/mcp/gateway.py`) adhering strictly to [`docs/ORCHESTRATOR_SPEC.md`](docs/ORCHESTRATOR_SPEC.md):

* **Exact 5 Verbs**:
  1. `ask_law`: Sovereign California statutory search, multi-hop precedence resolution, and tenant defense checklists (delegated to KruschLaw).
  2. `ask_biz`: Sovereign corporate contract intelligence, relational deal graph walk, and clause retrieval.
  3. `check_compliance`: Direct conflict analysis ("The Join") evaluating contract slots against statutory floors/ceilings (e.g., AB 12 deposit caps).
  4. `ingest`: Sovereign document ingestion with MIME magic byte verification and natural section boundary chunking.
  5. `purge`: Verifiable cryptographic deletion with SHA-256 tombstone audit receipts.
* **Token Budget**: Strictly constrained to **<450 prompt tokens** (~1,715 characters dense JSON) across all 5 verb definitions.
* **Launch Command**:
  ```bash
  python -m src.mcp.gateway
  ```

---

## 🎬 One-Command Reproduction Demo: The Amendment Blindspot

Standard vector RAG fails on corporate contract portfolios because verbose legal boilerplate in an original Master Services Agreement repeats domain query tokens 3–5x more frequently than a surgical 1-sentence amending restatement. Consequently, dense cosine and BM25 retrievers consistently rank the **superseded root agreement** over the **controlling amendment**—the *Amendment Blindspot*.

KruschBiz resolves this via **Precedence Graph Walking**:

```bash
# Run the standalone in-memory side-by-side reproduction demo (<10ms)
python3 scripts/demo_walk_vs_cosine.py
```

### Side-by-Side Comparison Output:
```
====================================================================================================
KRUSCH-BIZ PRECEDENCE ENGINE BENCHMARK: GRAPH WALK VS NAIVE COSINE RAG
====================================================================================================
Scenario: Acme Corp - Master Services Agreement (2024-01-15) amended by Amendment No. 1 (2024-06-01)
Query: 'What is Acme Corp's liability cap and payment term?'
----------------------------------------------------------------------------------------------------

1. NAIVE COSINE / BM25 FLAT RAG:
   ❌ Selected: 'MSA Section 9 (2024-01-15)' (Score: 0.942)
   ❌ Extracted Liability Cap: $500,000
   ❌ Extracted Payment Term: Net 30
   ⚠️  WHY IT FAILED (The Amendment Blindspot):
      The original 2024-01-15 MSA contains 180 words of verbose legal boilerplate repeating
      'liability', 'cap', 'payment', and 'terms' 7 times. The dense embedding and BM25 ranker
      favored lexical redundancy and length over legal precedence, completely missing the 1-sentence
      operative amendment executed 5 months later.

2. KRUSCH-BIZ RELATIONAL PRECEDENCE GRAPH WALK:
   ✅ Controlling Instrument: 'Amendment No. 1 (2024-06-01)'
   ✅ Lineage: MSA-2024 (SUPERSEDED by AMEND-01) -> AMEND-01 (CONTROLLING)
   ✅ Controlling Clause: 'Section 2 (Amended Liability & Payment)'
   ✅ Extracted Liability Cap: $1,000,000
   ✅ Extracted Payment Term: Net 45
   🛡️ WHY IT SUCCEEDED:
      KruschBiz resolved the confirmed 'AMENDS' edge from Amendment No. 1 to MSA-2024.
      Because the as-of query date (2024-07-01) is after Amendment No. 1's effective date,
      the graph walk pruned the superseded $500k / Net 30 clause and elevated the operative terms.
====================================================================================================
```

---

## 🛡️ Adversarial Multi-Document Evaluation Benchmark

KruschBiz is evaluated against an adversarial public fixture corpus of 7 complex multi-document corporate contract families (`data/eval/adversarial_corpus.json`) covering:
1. Verbose Master Agreements amended by surgical 1-sentence restatements.
2. Master Agreements conflicting with Statements of Work (SOWs) governed by precedence clauses.
3. Express carve-out and non-waiver provisions.
4. Unmarked side letters and addenda lacking explicit section references.
5. Expired agreements vs operative renewals with overlapping counterparty names.
6. Similar counterparties with subtle corporate entity suffixes (Inc vs LLC vs Ltd).
7. Conflicting entire agreement / merger clauses.

The engine is benchmarked across **4 uncoupled, objective metrics** under the **Fixture Verification** evaluation class (deterministic CI validation against `data/eval/adversarial_corpus.json` with recorded SHA-256 fixture hash `6b5d2931...`; distinct from Gate 3 Held-Out evaluations):

| Metric | Target | Measured Score | Evaluation Notes |
|---|---|---|---|
| **1. Relation Extraction F1** | > 90.0% | **100.0%** (P: 100%, R: 100%) | Body-level & preamble extraction of `AMENDS`, `SUPERSEDES`, `INCORPORATES`, `CARVES_OUT` across 7 families |
| **2. Controlling Clause As-Of Accuracy** | > 90.0% | **100.0%** (13/13) | Precedence DAG walk resolving exact governing clauses across past, intermediate, and present as-of dates |
| **3. Slot Extraction Exact-Match** | > 90.0% | **100.0%** (15/15) | Exact value extraction for `net_days`, `uptime_pct`, `liability_cap`, `late_fee_pct` from controlling text |
| **4. Proposition Grounding Accuracy** | > 90.0% | **100.0%** (28/28) | Multi-class grounding verification (`VERIFIED`, `DIVERGENT_TERM`, `INVENTED_CLAUSE`, `SUPERSEDED_TERM`) |

```bash
# Execute adversarial fixture verification suite (publishes live scorecard to data/eval/adversarial_eval_results.json)
python3 scripts/eval_adversarial_corpus.py

# Run automated pytest verification gates
pytest tests/eval/test_adversarial_corpus.py -v
```

---

## ⚖️ Cross-Engine Compliance Benchmark: The Join (`POST /conflicts/contract-vs-statute`)

KruschBiz integrates directly with KruschLaw to execute deterministic statutory compliance cross-examinations. Rather than delegating compliance analysis to probabilistic LLMs, **The Join** compares normalized contract slots resolved via the KruschBiz Precedence Graph against non-waivable statutory floors, ceilings, and prohibitions resolved via the KruschLaw Authority Graph.

```bash
# Execute the 1-command compliance benchmark suite (<50ms)
python3 scripts/eval_contract_vs_statute_join.py
```

### Evaluated Statutory Conflict Pairs:
| Benchmark ID | Test Scenario | Controlling Statute | Mandate Type | Deterministic Verdict |
|---|---|---|---|---|
| `TC-01` | **Post-AB 12 Security Deposit Violation** (2.0 mo demanded post-2024-07-01) | Cal. Civ. Code § 1950.5(c)(1) | Statutory Ceiling (1.0 mo) | `contract_less_than_mandatory` (`VOID_AS_AGAINST_PUBLIC_POLICY`) |
| `TC-02` | **Pre-AB 12 Security Deposit Compliance** (2.0 mo demanded pre-2024-07-01) | Cal. Civ. Code § 1950.5(c) (Prior) | Statutory Ceiling (2.0 mo) | `aligned` (`ENFORCEABLE`) |
| `TC-03` | **Sub-Statutory Landlord Entry Notice** (12 hrs vs 24 hr floor) | Cal. Civ. Code § 1954(d)(1) | Statutory Floor (24.0 hrs) | `contract_less_than_mandatory` (`VOID_AS_AGAINST_PUBLIC_POLICY`) |
| `TC-04` | **More Generous Entry Notice** (48 hrs vs 24 hr floor) | Cal. Civ. Code § 1954(d)(1) | Statutory Floor (24.0 hrs) | `contract_more_generous` (`ENFORCEABLE`) |
| `TC-05` | **Extended Deposit Return Timeline** (45 days vs 21-day ceiling) | Cal. Civ. Code § 1950.5(g)(1) | Statutory Ceiling (21 days) | `contract_less_than_mandatory` (`VOID_AS_AGAINST_PUBLIC_POLICY`) |
| `TC-06` | **Expedited Deposit Return Timeline** (14 days vs 21-day ceiling) | Cal. Civ. Code § 1950.5(g)(1) | Statutory Ceiling (21 days) | `contract_more_generous` (`ENFORCEABLE`) |
| `TC-07` | **Prohibited Habitability Waiver** (repair-and-deduct disclaimer) | Cal. Civ. Code § 1942.1 | Statutory Prohibition | `contract_less_than_mandatory` (`VOID_AS_AGAINST_PUBLIC_POLICY`) |
| `TC-08` | **Prohibited Retaliation Waiver** (retaliation defense disclaimer) | Cal. Civ. Code § 1942.5(h) | Statutory Prohibition | `contract_less_than_mandatory` (`VOID_AS_AGAINST_PUBLIC_POLICY`) |
| `TC-09` | **Excessive Late Fee Liquidated Damages** (15% vs 5% ceiling) | Cal. Civ. Code § 1671(d) | Statutory Ceiling (5.0%) | `contract_less_than_mandatory` (`VOID_AS_AGAINST_PUBLIC_POLICY`) |
| `TC-10` | **Commercial Lease Deposit Flexibility** (3.0 mo base rent) | Cal. Civ. Code § 1950.7(f) | Permissive Waiver | `aligned` (`ENFORCEABLE`) |
| `TC-11` | **Untracked Statutory Topic Coverage Gap** (`MUNICIPAL_SIDEWALK`) | None (Corpus Hole) | Coverage Gap | `coverage_gap` (`UNSPECIFIED`) |

---

## 🔒 Security Architecture & Local-First Guarantees

KruschBiz enforces defense-in-depth security to protect confidential commercial contracts:

1. **Loopback-Only Service Bindings**:
   - Backend API defaults strictly to `127.0.0.1:8086`.
   - Frontend UI defaults strictly to `127.0.0.1:8506`.
   - Startup hooks verify loopback bindings; public network exposure is blocked by design.
2. **Pre-Spool MIME Magic Byte Verification**:
   - Ingestion endpoints inspect binary file headers (`%PDF-`, `PK\x03\x04`, `\xd0\xcf\x11\xe0`) before spooling to disk.
   - Executable binaries (`MZ`, `\x7fELF`) and unrecognized formats are immediately rejected with HTTP 400.
3. **Path Traversal & Filename Sanitization**:
   - Document upload filenames are sanitized using secure basename extraction; directory traversal (`../`) attempts are neutralized.
4. **Multi-Tenant Isolation & Anti-Spoofing**:
   - Requests outside development require key-bound tenant authentication (`tenant_id:key_secret`).
   - Unauthenticated `X-Tenant-ID` header spoofing is rejected with HTTP 403 Forbidden.
   - All database queries, full-text searches, and graph traversals are tenant-partitioned (`tenant_id == active_tenant`).
   - Cross-tenant IDOR mutations or deletions return HTTP 404 Not Found.
   - Comprehensive test suite (`tests/test_tenant_isolation.py`) enforces strict tenant boundary isolation across 8 distinct vectors.
5. **Air-Gapped Local Inference**:
   - Zero outbound telemetry or cloud API calls. Embeddings (`bge-large`) and generation (`qwen2.5-coder:14b` / `7b`) execute locally via Ollama or on-prem GPU nodes.

---

## 🧪 Automated Testing & CI Gates

```bash
# Run full unit, integration, graph invariant, compliance join, tagger, security, and tenant isolation test suite (162 tests)
pytest tests

# Run golden precedence graph invariant tests (confirmed-edge walk, draft isolation, hierarchy)
pytest tests/test_graph_invariants.py -v

# Run The Join tests (Contract vs. Statute compliance evaluation, AB 12, entry floors)
pytest tests/test_compliance_join.py -v

# Run Gateway MCP router tests (5-verb gateway, <450 token budget, JSON-RPC)
pytest tests/test_gateway_mcp.py -v

# Run domain MCP server tests (verifies 4 canonical tools)
pytest tests/test_mcp.py

# Run adversarial grounding test suite (16 adversarial cases)
pytest tests/test_adversarial_grounding.py

# Run security hardening tests (tenant binding, rate limiting, magic bytes, constant vector refusal)
pytest tests/test_security_hardening.py

# Run multi-tenant isolation tests (8 vectors)
pytest tests/test_tenant_isolation.py -v

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

