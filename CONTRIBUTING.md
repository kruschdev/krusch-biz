# 🤝 Contributing to KruschBiz

Welcome, and thank you for contributing to KruschBiz!

KruschBiz is an air-gapped, sovereign commercial contract precedence graph and slot grounding engine. Because our users rely on deterministic legal precedence and strict mathematical grounding, all contributions must uphold non-negotiable architectural invariants.

---

## 🏛️ Core Principles & Boundaries

1. **Air-Gap Compliance (Zero External Cloud I/O)**:
   - KruschBiz never makes outbound requests to third-party public cloud APIs, hosted LLM endpoints, telemetry trackers, or external servers.
   - All models run locally on loopback via Ollama or in headless mock mode.
2. **Confirmed-Edge Only Precedence**:
   - Proposed edges (`status='proposed'`) must never alter governing terms in the resolver. Precedence resolution walks strictly confirmed edges (`status='confirmed'`).
3. **No Silent Keyword Fallback**:
   - Keyword search is strictly exploratory RAG and cannot promote a clause to controlling authority.
4. **Zero-Trust Multi-Tenancy**:
   - All state, queries, and mutations partition strictly by `tenant_id`. Every new table or route must enforce tenant isolation.
5. **Frozen 4-Call Public Boundary (v0.1)**:
   - The public contract is frozen to:
     - `resolve_controlling_clause(tenant_id, counterparty, topic, as_of_date)`
     - `verify_grounding(tenant_id, assertion, controlling_clause, amendment_trail)`
     - `ingest_contract(file_bytes, filename, tenant_id, counterparty, doc_type, effective_date)`
     - `confirm_relation(tenant_id, relation_id)`
   - Any modifications to these signatures require formal review and an architectural deprecation cycle.

---

## 🛠️ Local Development Setup

### 1. Clone & Virtual Environment
```bash
git clone https://github.com/kruschdev/krusch-biz.git
cd krusch-biz
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Run in Headless Mode (Zero GPU / Zero Dependencies)
KruschBiz ships with a bundled SQLite database (`data/demo.db`) and deterministic vector generation:
```bash
HEADLESS_MODE=1 uvicorn src.backend.main:app --host 127.0.0.1 --port 8086
```
Visit `http://127.0.0.1:8086/docs` to interact with the API immediately.

---

## 🧪 Verification & Test Suite

Before opening a pull request, all automated test batteries must pass:

### 1. Run Complete Test Suite
```bash
pytest tests/ -v
```

### 2. Run Core Invariant Tests
```bash
pytest tests/test_graph_invariants.py tests/test_tenant_isolation.py tests/test_security_hardening.py -v
```

### 3. Run the 30-Family Adversarial Benchmark
```bash
python scripts/eval_adversarial_corpus.py
```
*Note: Any change causing failures or regressions in the 30-family benchmark will block CI merge.*

### 4. Code Quality & Formatting
```bash
ruff check .
```

---

## 📋 Pull Request Checklist

When submitting a pull request, ensure your branch passes all items in this checklist:

- [ ] **Tests Passing**: Full test suite passes cleanly with zero errors (`pytest tests/`).
- [ ] **Zero Failures on Adversarial Benchmark**: `python scripts/eval_adversarial_corpus.py` reports 0 failures across all 30 families.
- [ ] **Invariant Conformance**: Code does not violate any rules documented in [`docs/INVARIANTS.md`](docs/INVARIANTS.md).
- [ ] **Zero Cloud I/O**: No third-party public cloud network calls or unapproved libraries added.
- [ ] **Public Boundary Respected**: No leaky internal functions exposed without explicit justification.
- [ ] **Changelog Updated**: Brief description added under `## [Unreleased]` in [`CHANGELOG.md`](CHANGELOG.md).
