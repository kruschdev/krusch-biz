# 🛡️ KruschBiz Core Invariants & Pass/Fail Test Matrix

> **Authoritative Specification**: This document establishes the non-negotiable architectural invariants of KruschBiz. Every invariant is paired with deterministic, pass/fail automated regression tests.

---

## 📋 The Invariants Matrix

| # | Invariant Name | Failure Mode if Violated | Enforcing Test(s) | Status |
|---|---|---|---|---|
| **INV-1** | **Confirmed-Edge Only** | Proposed/unconfirmed relations silently alter governing terms or precedence | `tests/test_graph_invariants.py::TestGraphInvariants::test_01_confirmed_edge_invariant`<br>`tests/test_resolver.py::TestPrecedenceResolver::test_02_unconfirmed_relation_ignored` | ✅ PASS |
| **INV-2** | **Draft Isolation** | Unexecuted or draft instruments defeat or supersede executed agreements | `tests/test_graph_invariants.py::TestGraphInvariants::test_03_draft_isolation_invariant`<br>`tests/test_resolver.py::TestPrecedenceResolver::test_03_draft_isolation`<br>`tests/eval/test_adversarial_corpus.py (family_20_unexecuted_draft)` | ✅ PASS |
| **INV-3** | **Cycle Fail-Closed** | Circular amendment graphs (A → B → C → A) cause infinite loops or arbitrary choices | `tests/test_graph_invariants.py::TestGraphInvariants::test_02_cycle_detection_fail_closed`<br>`tests/test_resolver.py::TestPrecedenceResolver::test_04_cycle_fail_closed` | ✅ PASS |
| **INV-4** | **No Silent Keyword Promotion** | Keyword/lexical match promotes an unconfirmed or lower-precedence clause to controlling | `tests/test_graph_invariants.py::TestGraphInvariants::test_05_no_silent_keyword_promotion`<br>`tests/test_resolver.py::TestPrecedenceResolver::test_08_no_keyword_controlling_fallback` | ✅ PASS |
| **INV-5** | **Zero-Trust Tenant Isolation** | Cross-tenant data leakage between partitioned corporate workspaces | `tests/test_tenant_isolation.py (8/8 tests)`<br>`tests/test_api.py::TestAPI::test_09_tenant_isolation` | ✅ PASS |
| **INV-6** | **Immutable Append-Only Audit** | Administrative tampering or deletion of historical deal audit events | `tests/test_security_hardening.py::TestSecurityHardening::test_01_audit_log_append_only`<br>`tests/test_db.py::TestDatabase::test_06_audit_log_immutable` | ✅ PASS |
| **INV-7** | **Pre-Spool Magic-Byte Gate** | Polyglot files, executable binaries, or HTML disguised as contract PDFs | `tests/test_security_hardening.py::TestSecurityHardening::test_03_magic_byte_rejection`<br>`tests/eval/test_adversarial_corpus.py (family_14_html_disguised_pdf)` | ✅ PASS |
| **INV-8** | **Canonical Grounding Taxonomy** | Hallucinated slots or uncited numeric claims pass verification silently | `tests/test_adversarial_grounding.py (25/25 tests)`<br>`tests/test_grounding_properties.py (5/5 property tests)`<br>`tests/eval/test_adversarial_corpus.py (30/30 families)` | ✅ PASS |
| **INV-9** | **Frozen 4-Call Public API** | Leaky operational APIs dilute the core contract precedence product | `tests/test_api.py`<br>`tests/test_mcp.py`<br>`tests/eval/test_golden_eval_gate.py` | ✅ PASS |
| **INV-10** | **Legal Hold & Strict Data Residency** | Matters under legal hold purged; production processes leak outside loopback | `tests/test_security_hardening.py (test_13, test_14, test_15)` | ✅ PASS |

---

## 🔍 Detailed Invariant Specifications

### INV-1: Confirmed-Edge Only Precedence
* **Requirement**: Ingestion and relationship extraction pipeline may propose edges with `status='proposed'`. The precedence resolver (`resolve_controlling_clause`) **must strictly filter** `AgreementRelation.status == 'confirmed'`.
* **Behavior**: Unconfirmed proposals are returned solely inside `proposed_relations_advisory` and never modify the precedence walk, controlling document, or controlling clause.
* **Verification Command**:
  ```bash
  pytest tests/test_graph_invariants.py -k "test_01_confirmed_edge_invariant"
  ```

### INV-2: Unexecuted Draft Isolation
* **Requirement**: Instruments with `execution_status='draft'` or `'unexecuted'` must never defeat, supersede, or amend executed agreements.
* **Behavior**: When an executed agreement is amended by a draft agreement, the resolver isolates the draft and continues to recognize the executed agreement as controlling, emitting a draft isolation notice in `resolution_warnings`.
* **Verification Command**:
  ```bash
  pytest tests/test_graph_invariants.py -k "test_03_draft_isolation_invariant"
  ```

### INV-3: Cycle Detection & Fail-Closed Precedence
* **Requirement**: Any circular reference in `AMENDS` or `SUPERSEDES` relationships (e.g. Agreement A amends B, B amends C, C amends A) must be detected deterministically.
* **Behavior**: The resolver maintains a recursion stack set during depth-first traversal and enforces a hard recursion depth limit (`depth < 32`). Upon cycle detection, it:
  1. Truncates the traversal to prevent infinite recursion.
  2. Sets `resolution_quality = 0.0`.
  3. Sets `competing_peer_detected = True`.
  4. Records the exact cycle path in `resolution_warnings`.
* **Verification Command**:
  ```bash
  pytest tests/test_graph_invariants.py -k "test_02_cycle_detection_fail_closed"
  ```

### INV-4: No Silent Keyword Promotion
* **Requirement**: Controlling status is an authority hierarchy and chronological topological walk, **never** a text-similarity or keyword retrieval result.
* **Behavior**: If no clause in the controlling document family is tagged with the target canonical topic, `resolve_controlling_clause` returns `controlling_clause = None` with `resolution_warnings = ["NO_TOPIC_CLAUSE_IN_CONTROLLING_DOCUMENT"]`. It **never** executes a fallback substring/ILIKE search to pick an arbitrary clause from another agreement.
* **Verification Command**:
  ```bash
  pytest tests/test_graph_invariants.py -k "test_05_no_silent_keyword_promotion"
  ```

### INV-5: Zero-Trust Multi-Tenant Isolation
* **Requirement**: All database entities (`agreements`, `clauses`, `agreement_relations`, `deal_evidence`, `audit_logs`, `materialized_effective_slots`) must partition by `tenant_id`.
* **Behavior**: Resolving, searching, or verifying clauses under Tenant A will never return or consider records belonging to Tenant B, even when agreements share identical counterparties or timestamps.
* **Verification Command**:
  ```bash
  pytest tests/test_tenant_isolation.py
  ```

### INV-6: Append-Only Immutable Audit Trail
* **Requirement**: Compliance records and deal audit events must be cryptographically durable and tamper-evident.
* **Behavior**: SQLAlchemy event listeners intercept `before_update` and `before_delete` on `AuditLog` and raise `PermissionError("AuditLog records are append-only and cannot be modified or deleted.")`.
* **Verification Command**:
  ```bash
  pytest tests/test_security_hardening.py -k "test_01_audit_log_append_only"
  ```

### INV-7: Pre-Spool MIME Magic-Byte Verification
* **Requirement**: Reject polyglot attacks, shell scripts, executable binaries, and HTML masquerading as contract PDFs before spooling files to disk or parsing.
* **Behavior**: Inspects the first 512 bytes of any uploaded payload. Rejection criteria:
  - Executables: Windows PE (`MZ`), Linux ELF (`\x7fELF`), macOS Mach-O (`\xfe\xed\xfa\xce`, `\xcf\xfa\xed\xfe`).
  - Disguised HTML: `<html`, `<!doctype`, `<script`.
  - Allowed types: PDF (`%PDF-`), DOCX (`PK\x03\x04`).
* **Verification Command**:
  ```bash
  pytest tests/test_security_hardening.py -k "test_03_magic_byte_rejection"
  ```

### INV-8: Canonical Proposition Grounding & Numeric Verification
* **Requirement**: Every generated commercial statement must be audited against the controlling authority set.
* **Behavior**:
  - Uncited numeric statements must match a structured slot in the controlling clause; otherwise, they fail with `UNCITED_NUMERIC_CLAIM`.
  - Conflicting numeric values fail with `SLOT_MISMATCH`.
  - Conflicting currency/units fail with `UNIT_MISMATCH`.
  - Assertions citing superseded instruments fail with `SUPERSEDED` / `SUPERSEDED_TERM`.
  - Non-existent citations fail with `INVENTED_CLAUSE` / `NO_AUTHORITY`.
* **Verification Command**:
  ```bash
  pytest tests/test_adversarial_grounding.py tests/test_grounding_properties.py
  ```

### INV-9: Frozen 4-Call Public API Surface
* **Requirement**: The public API surface of KruschBiz is frozen to 4 high-leverage primitives:
  1. `resolve_controlling_clause(tenant_id, counterparty, topic, as_of_date)`
  2. `verify_grounding(tenant_id, assertion, controlling_clause, amendment_trail)`
  3. `ingest_contract(file_bytes, filename, tenant_id, counterparty, doc_type, effective_date)`
  4. `confirm_relation(tenant_id, relation_id)`
* **Behavior**: Exposed via Python SDK, REST API (`/api/agreements/*`), and MCP server (`src/mcp/server.py`). All other endpoints are operational diagnostics or internal helpers.
* **Verification Command**:
  ```bash
  pytest tests/test_api.py tests/test_mcp.py
  ```

---

## 🚀 Running the Full Invariant Suite

To execute the entire 194-test regression battery enforcing all invariants:
```bash
pytest tests/ -v
```
To run the 30-family adversarial multi-document benchmark:
```bash
python scripts/eval_adversarial_corpus.py
```
