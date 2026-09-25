# 🏛️ KruschBiz Architecture

Technical architecture specification for **KruschBiz**: a confirmed-edge contract precedence graph with deterministic slot grounding and air-gapped sovereign corporate intelligence.

---

## 1. System Overview & Product Boundary

KruschBiz is engineered for **one single product**:
> **A confirmed-edge contract precedence graph with slot grounding and assertion verification.**

Operational services like invoicing, accounts receivable aging, OCR, and general template drafting have been excised to sibling packages. KruschBiz focuses strictly on determining which legal instruments and clauses govern a specific commercial relationship as of a given date, and verifying that LLM-generated assertions are mathematically grounded against those controlling terms.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INGESTION & GRAPH EXTRACTION                       │
│  Contracts (PDF, DOCX) ──► Magic-Byte Check ──► Parser ──► Structured Slots │
│                                                                  │          │
│                                                                  ▼          │
│  Candidate Relations ◄── Extractor ──► Proposed Edges (status='proposed')   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ (Human-in-the-Loop Confirmation)
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONFIRMED-EDGE PRECEDENCE GRAPH                       │
│  Agreements Node ──► Clauses Node ──► Confirmed Edges (status='confirmed')  │
│  (Instrument Types: master_agreement, amendment, statement_of_work, etc.)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      CONTROLLING DOCUMENT RESOLVER (DAG)                     │
│  resolve_controlling_clause(counterparty, topic, as_of_date)                │
│  - Walks ONLY confirmed edges                                               │
│  - Cycle detection (DFS recursion stack + depth cap 32 + self-loop check)   │
│  - Draft isolation (execution_status='draft' never defeats executed)        │
│  - Hierarchy precedence (SOW controls fees/SLAs; MSA controls governance)   │
│  - Emits immutable ResolutionTraceRecord + amendment_trail                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SLOT GROUNDING & VERIFICATION SCANNER                    │
│  verify_commercial_grounding(assertion, retrieved_controlling_clauses)      │
│  - Validates citation against retrieved controlling set                     │
│  - Normalizes slot values (currency, basis points, interest periods)        │
│  - 7 Canonical Failure Modes: WRONG_INSTRUMENT, SLOT_MISMATCH,             │
│    UNIT_MISMATCH, NEGATED_OBLIGATION, PARTIAL_SUPPORT, SUPERSEDED,          │
│    NO_AUTHORITY                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Graph Data Model & State Transitions

### Models (`src/backend/db.py`)
1. **`Agreement` (`agreements`)**: Represents a physical or digital legal instrument.
   - `instrument_type`: `master_agreement`, `amendment`, `statement_of_work`, `schedule`, `addendum`, `side_letter`, `exhibit`.
   - `execution_status`: `executed`, `draft`, `unexecuted`, `terminated`.
   - `status`: `active`, `superseded`, `terminated`, `expired`.
   - `effective_date`, `expiration_date`.
2. **`Clause` (`clauses`)**: Normalized section or clause within an agreement.
   - `authority_class`: `governing_agreement`, `amendment`, `statement_of_work`, etc.
   - `topic`: Canonical commercial topic (e.g. `PAYMENT_TERMS`, `LIMITATION_OF_LIABILITY`, `FEES`).
   - `structured_slots`: Extracted quantitative parameters (e.g. `{"net_days": 30, "late_interest_pct": 1.5}`).
   - `clause_uid`: Deterministic 32-character SHA-256 hash.
3. **`AgreementRelation` (`agreement_relations`)**: Directed relation between two instruments.
   - `source_agreement_id` ──(`relation_type`)──► `target_agreement_id`
   - `relation_type`: `SUPERSEDES`, `AMENDS`, `SCHEDULE_OF`, `STATEMENT_OF_WORK`, `CARVES_OUT`, `INCORPORATES`.
   - `clause_scope`: Scope filter (`ALL`, `Section 8.1`, `topic:FEES`).
   - `status`: `proposed` | `confirmed` | `rejected`.

### Edge Lifecycle & Invariant
```
         Extract / Ingest
                 │
                 ▼
        ┌─────────────────┐
        │ status='proposed'│  ◄── Never alters controlling clause in resolver
        └────────┬────────┘
                 │ Human Review / API Call
                 ├──────────────────────────────┐
                 ▼                              ▼
        ┌──────────────────┐          ┌───────────────────┐
        │ status='confirmed│          │  status='rejected' │
        └──────────────────┘          └───────────────────┘
                 │                              │
                 ▼                              ▼
     Walked by Precedence Resolver        Permanently Ignored
```
- **The Confirmed-Edge Invariant**: `resolve_controlling_clause` strictly filters `AgreementRelation.status == 'confirmed'`. Proposed edges are returned only as non-binding advisories (`proposed_relations_advisory`).

---

## 3. Precedence Resolver Algorithm (`src/backend/resolver.py`)

Given `(tenant_id, counterparty, topic, as_of_date)`:

1. **Counterparty Isolation**: Resolves canonical entity and aliases via `Party` / `PartyAlias`. Strictly isolates instruments across counterparties.
2. **Temporal Validity Filtering**: An agreement is candidate-eligible if:
   - `ag.effective_date <= as_of_date` (or `None`).
   - `ag.expiration_date is None` or `ag.expiration_date > as_of_date`.
   - `ag.execution_status != 'draft'` (unless explicitly resolving draft diffs).
3. **Transitive Supersession Closure**:
   - Gathers all `SUPERSEDES` edges where `status='confirmed'`.
   - Executes DFS recursion-stack cycle detection to ensure acyclic structure.
   - Computes transitive closure of fully superseded agreements (`clause_scope in ('ALL', '*')`) and scoped supersessions.
   - Draft instruments can never supersede executed instruments.
4. **Amendment DAG Walk**:
   - For each active base clause, traverses incoming `AMENDS` edges chronologically by effective date.
   - Merges structured slots forward down the amendment chain (slot inheritance).
   - Enforces a recursion limit (`depth < 32`), self-loop check (`source == target`), and path-cycle checks. If a cycle is detected, returns status `GRAPH_CYCLE` and logs a `ContractConflictRecord`.
5. **Order of Precedence (SOW vs MSA)**:
   - If both a Statement of Work / Schedule and a Master Agreement survive:
     - For operational topics (`FEES`, `PAYMENT_TERMS`, `DELIVERABLES`, `HOURLY_RATES`, `PRICING`), the SOW / Schedule controls.
     - For legal governance topics (`LIMITATION_OF_LIABILITY`, `INDEMNITY`, `GOVERNING_LAW`), the Master Agreement controls.
6. **Immutable Resolution Tracing**:
   - Persists a `ResolutionTraceRecord` to `resolution_traces` capturing the winning clause, amendment hops evaluated, defeating candidates, and full audit rationale.

---

## 4. Frozen Clause UID Schema

The canonical clause fingerprint is deterministically computed via:
```python
def compute_clause_uid(
    instrument_family: str,
    canonical_topic: str,
    clean_slots: dict[str, Any] | None = None,
    restates_clause_id: str | None = None
) -> str:
    norm_family = normalize_party_name(instrument_family)
    norm_topic = canonical_topic.strip().upper()
    slots_str = json.dumps(clean_slots or {}, sort_keys=True)
    restate_str = str(restates_clause_id) if restates_clause_id else ""
    raw = f"{norm_family}|{norm_topic}|{slots_str}|{restate_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
```
This hash is frozen and verified in unit tests (`test_09_clause_uid_schema_and_frozen_hash`). Any change to field serialization or truncation constitutes a major schema migration.

---

## 5. Grounding Verification Taxonomy (`src/backend/rag.py`)

Assertions generated by LLMs are audited against retrieved controlling clauses and classified into **7 canonical failure codes**:

| Failure Code | Description | Example |
|---|---|---|
| `WRONG_INSTRUMENT` | Cited instrument does not exist or is not controlling for this matter. | Citing Vendor B's contract in a matter with Vendor A. |
| `SLOT_MISMATCH` | Clause exists, but quantitative slot values diverge. | Contract says Net 30; draft asserts Net 60. |
| `UNIT_MISMATCH` | Numerical value matches, but units, currency, or period diverge. | 1.5% monthly late fee cited as 1.5% annual interest. |
| `NEGATED_OBLIGATION` | Obligation is negated, conditioned, or stripped of carve-outs. | Omitting gross negligence carve-out from liability cap. |
| `PARTIAL_SUPPORT` | Topic matches, but specific claims lack factual backing. | Stating SLA credits are doubled without contract support. |
| `SUPERSEDED` | Clause was valid historically, but superseded as of the query date. | Relying on 2021 MSA terms modified by 2023 Amendment. |
| `NO_AUTHORITY` | Invented or phantom section numbers with no text in the graph. | Citing non-existent Section 99.9. |

---

## 6. Security Boundaries & Sovereign Air-Gap

1. **Loopback Binding**: Services default strictly to `127.0.0.1`. Non-loopback bindings (`0.0.0.0`) raise `RuntimeError` at boot unless `ALLOW_LAN=1` is explicitly set.
2. **Production Key Enforcement**: When `APP_ENV != 'development'`, boot fails if `API_KEY` is missing, empty, or set to placeholder values (`default`, `changeme`, `secret`, `kruschbiz_secret`).
3. **Tenant Authentication & Anti-Spoofing**: Keys are bound to specific tenants (`tenant_id:key_secret`). Mismatched `X-Tenant-ID` headers are rejected with HTTP 403.
4. **MIME Magic Byte Allowlist**: Ingestion checks file magic bytes before disk spooling, rejecting `MZ` (Windows PE), `\x7fELF` (Linux ELF), Mach-O binaries, and HTML disguised as `.pdf`.
5. **Append-Only Immutability**: `AuditLog` records reject `UPDATE` and `DELETE` via SQLAlchemy database event listeners.
6. **Transactional Purge**: `purge_deal_matter_transactional` and `purge_agreement_transactional` atomically delete all associated records, guaranteeing zero orphan rows.

---

## 7. Model Context Protocol (MCP) Surface

KruschBiz exposes a clean dual-surface MCP interface:

### 1. Domain MCP Server (`src/mcp/server.py`) — 4 Canonical Tools
- `contract_intelligence`: Execute hybrid search, controlling-document DAG resolution, and conflict detection.
- `manage_deal`: Create and audit corporate deal matters, ingest exhibits, and track due diligence.
- `ingest_contract`: Ingest agreements and deal evidence with magic byte validation and slot extraction.
- `verify_grounding`: Audit proposed draft text against retrieved controlling clauses with 7-code failure taxonomy.

### 2. Sovereign Gateway Router (`src/mcp/gateway.py`) — 5 Sovereign Verbs
Consolidated sovereign gateway strictly budgeted to **<450 prompt tokens** (~428 tokens) for local 7B/14B inference:
- `ask_law`: Statutory precedence and regulatory RAG (delegated to KruschLaw).
- `ask_biz`: Relational contract graph search and controlling clause resolution.
- `check_compliance`: Direct contract-vs-statute join and floor/ceiling violation analysis.
- `ingest`: Sovereign file ingestion pipeline with SHA-256 verification.
- `purge`: Transactional data purge with SHA-256 tombstone audit trail.
