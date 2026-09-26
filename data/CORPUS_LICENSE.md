# 📜 Evaluation Corpus License & Data Provenance

> **Authoritative Compliance Statement**: This document defines the legal provenance, copyright status, and usage licensing for all contract corpora, eval fixtures, and demo databases bundled within KruschBiz.

---

## 1. Provenance Classifications

All contract texts in `data/` and `data/eval/` belong to one of two strictly documented, non-confidential categories:

### Category A: SEC EDGAR Public Domain Filings (Exhibits 10)
- **Source**: U.S. Securities and Exchange Commission (SEC) EDGAR public corporate disclosures filed pursuant to 17 CFR § 229.601 (Item 601 - Exhibits, specifically Exhibit 10 material contracts).
- **Legal Status**: Public government records in the United States, free of proprietary secrecy or confidentiality covenants.
- **Fair Use & Reproduction**: Evaluated and reproduced under 17 U.S.C. § 107 for automated research, software benchmarking, and information retrieval evaluation.
- **Redaction Policy**: All individual personal names, private residential addresses, phone numbers, and bank account coordinates have been redacted or replaced with synthetic placeholders.

### Category B: Synthetic Adversarial Fixtures
- **Source**: 100% synthetically authored by the KruschBiz engineering team specifically designed to test algorithmic edge cases (e.g. `family_08` through `family_30` in `data/eval/adversarial_corpus.json`).
- **Composition**: Structured legal mock text containing targeted edge cases:
  - Scoped partial amendments (overriding Section 4.1 while preserving Section 4.2).
  - Unexecuted draft collisions (draft amendments vs executed agreements).
  - Currency and basis point mismatches (USD vs EUR, Net 30 vs Net 45).
  - Cyclic amendment traps and three-hop transitive DAG walks.
- **Licensing**: Released under the **Creative Commons Attribution 4.0 International (CC-BY-4.0)** license and dual-licensed under the **MIT License**.

---

## 2. Zero Confidential Client Data Warranty

The authors of KruschBiz warrant that:
1. **Zero Client Data**: No confidential, privileged, attorney-client, or non-public commercial agreements from any private enterprise or client matter are included in this repository.
2. **Deterministic Reproducibility**: Third-party auditors, corporate counsel, and open-source contributors can freely clone, execute, inspect, and redistribute the benchmark fixtures without intellectual property infringement or exposure to trade secrets.

---

## 3. Bundled SQLite Demo (`data/demo.db`)

The pre-seeded SQLite database file (`data/demo.db`) is derived strictly from the Category B synthetic fixtures and public EDGAR demonstration templates. It contains:
- 6 synthetic commercial instruments (`Acme Corp`, `Global Logistics Ltd`, `Beta SaaS`).
- 13 tagged clauses with deterministic unit pseudo-embeddings.
- Pre-confirmed and proposed relationship edges for interactive UI and API evaluation.
