# Krusch Intelligence Suite: Sovereign Orchestrator Specification

> **Version**: 1.0.0-draft  
> **Status**: Authoritative Architectural Contract  
> **Scope**: Binds `krusch-law` (Statutory Authority Graph) and `krusch-biz` (Commercial Contract Graph).

---

## 1. The Core Ecosystem Boundary

`krusch-law` and `krusch-biz` do not share databases, vector tables, or process spaces. They are independent sovereign domains coordinated exclusively via typed reference mappings, shared temporal parameters, and a single join contract.

```
┌────────────────────────────────┐                 ┌────────────────────────────────┐
│          KRUSCH-LAW            │                 │          KRUSCH-BIZ            │
│    Public Statutory Graph      │                 │    Private Relational Graph    │
│   (Ordinances, Preemptions)    │                 │    (Amendments, Precedence)    │
│    Database: kruschlaw (SQLite)│                 │   Database: kruschbiz (5436)   │
└───────────────┬────────────────┘                 └───────────────┬────────────────┘
                │                                                  │
                └─────────────────────────┬────────────────────────┘
                                          ▼
                      ┌───────────────────────────────────────┐
                      │          ORCHESTRATOR JOIN            │
                      │    POST /conflicts/contract-vs-stat   │
                      │                                       │
                      │ Resolves contract clause vs governing │
                      │ mandatory statute under as_of_date    │
                      └───────────────────────────────────────┘
```

---

## 2. Reference Mapping (`matter_ref` ↔ `deal_ref`)

When an attorney or executive examines an operational file, the orchestrator bridges them via an explicit mapping table:

| Field Name | Type | Domain | Description | Example |
|---|---|---|---|---|
| `matter_ref` | `string` | KruschLaw | Client matter identifier / docket tracking number | `MAT-2026-088` |
| `deal_ref` | `string` | KruschBiz | Commercial transaction / contract family code | `DEAL-ACME-LEASE` |
| `jurisdiction` | `string` | Shared | Two-letter state + municipal identifier | `CA:Oakland` |
| `counterparty` | `string` | Shared | Legal name of contracting counterparty | `Acme Property Holdings, LLC` |
| `as_of_date` | `string` | Shared | Mandatory ISO-8601 valuation/incident date | `2024-08-01` |

**Rule**: Neither database stores foreign keys referencing the other. The mapping lives in the Orchestrator runtime registry.

---

## 3. Query Ownership Matrix

Local models (7B/14B) must route to the owning server based strictly on the question class:

| Question Class | Owning Server | Controlling Model / Artifact | Rejection Invariant |
|---|---|---|---|
| **Statutory Law & Ordinances** | `krusch-law` | `StatutoryArtifact` + Precedence Resolver | Refuse if no confirmed statutory pack covers jurisdiction |
| **Contract Terms & Amendments** | `krusch-biz` | `Agreement` DAG + Controlling Clause Resolver | Refuse if retrieved authorities are unexecuted drafts |
| **Contract vs. Statute Legality** | **The Join** | Dual-Resolver Comparator | Refuse if `as_of_date` or `jurisdiction` is omitted |
| **Client Discovery Exhibits** | `krusch-law` | `MatterEvidence` (Encrypted at rest) | Refuse search against public statutory indices |
| **Deal Room Due Diligence** | `krusch-biz` | `DealEvidence` (Encrypted at rest) | Refuse cross-tenant queries without key authorization |

---

## 4. The High-Value Join: `POST /conflicts/contract-vs-statute`

The single functional justification for running both engines simultaneously is testing whether a private contractual term violates a non-waivable statutory mandate.

### Request Contract
```json
{
  "deal_id": 14,
  "matter_id": 8,
  "jurisdiction": "CA:Oakland",
  "as_of_date": "2024-08-15",
  "topics": ["SECURITY_DEPOSIT", "LATE_FEE", "ENTRY_NOTICE"]
}
```

### Execution Pipeline
1. **Biz Resolution**: Query `resolve_controlling_clause(deal_id, topic, as_of_date)` walking confirmed `AMENDS` / `SUPERSEDES` edges on executed agreements. Extract normalized slot (e.g. `deposit_cap_months: 2.0`).
2. **Law Resolution**: Query `resolve_controlling_law(topic, jurisdiction, as_of_date)`. Extract statutory ceiling (e.g. AB 12 caps deposits at `1.0` months rent after `2024-07-01`).
3. **Deterministic Evaluation**: Compare normalized slot against statutory rule:
   - `aligned`: Contract complies with statute.
   - `contract_more_generous`: Contract grants more rights than statutory floor (e.g. 48-hr entry notice vs 24-hr statutory minimum).
   - `contract_less_than_mandatory`: Contract violates non-waivable statute (e.g. demanding 2 months deposit when statute caps at 1 month).
   - `coverage_gap`: Statutory rule or contract clause absent from record.
   - `jurisdiction_mismatch`: Contract designates governing law preempted by local municipal ordinance.

### Response Contract
```json
{
  "verdict": "NON_COMPLIANT_TERMS_FOUND",
  "as_of_date": "2024-08-15",
  "findings": [
    {
      "topic": "SECURITY_DEPOSIT",
      "alignment": "contract_less_than_mandatory",
      "enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
      "contract_clause": {
        "instrument": "Master Lease 2024",
        "section": "Section 4.1",
        "span": "Tenant shall deposit an amount equal to two (2) months' rent ($6,000)...",
        "normalized_slot": {"max_months": 2.0}
      },
      "controlling_statute": {
        "citation": "Cal. Civ. Code § 1950.5(c)(1)",
        "effective_date": "2024-07-01",
        "mandate_type": "STATUTORY_CEILING",
        "span": "A landlord may not demand or receive security... in an amount exceeding one month's rent.",
        "normalized_slot": {"max_months": 1.0}
      },
      "trace_id": "trace_ab12_vs_lease_2024"
    }
  ]
}
```

---

## 5. Explicit Non-Negotiable Invariants ("DO NOT" List)

1. **NO VECTOR UNION**: Never merge statutory embeddings (`laws_vectors`) with private contract chunks (`clauses` / `deal_evidence`). They run on isolated tables with distinct access permissions.
2. **NO SILENT "TODAY"**: `as_of_date` is mandatory on all mutation and audit endpoints. The API must return `HTTP 422 Unprocessable Entity` if omitted in production.
3. **NO PROPOSED EDGES IN RESOLUTION**: Auto-extracted DAG relations (`AMENDS`, `SUPERSEDES`) must remain `status: 'proposed'` until confirmed by a human reviewer. The resolver **strictly evaluates confirmed edges**.
4. **NO UNEXECUTED WINNERS**: Agreements with `execution_status: 'draft'` or `'unknown'` cannot supersede or amend `'executed'` instruments.
5. **DETERMINISM OVER ENTAILMENT FOR NUMBERS**: Monetary amounts, interest percentages, and notice windows must be verified via regex and typed normalization (`int`/`float`). LLM semantic similarity is never used to confirm numerical parity.
