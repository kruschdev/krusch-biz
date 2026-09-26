## Description
<!-- Provide a clear, concise summary of the proposed changes and architectural context. -->

## Invariant Conformance & Checklist
- [ ] **Automated Test Suite**: All tests pass cleanly (`pytest tests/`).
- [ ] **Adversarial Benchmark**: Zero failures on 30-family corpus (`python scripts/eval_adversarial_corpus.py`).
- [ ] **Confirmed-Edge Invariant**: Verified that proposed edges cannot alter controlling precedence.
- [ ] **Draft Isolation**: Unexecuted drafts cannot defeat or amend executed instruments.
- [ ] **No Silent Keyword Fallback**: Controlling clauses are elected solely via graph topological walk.
- [ ] **Zero-Trust Multi-Tenancy**: Changes enforce strict partitioning by `tenant_id`.
- [ ] **Air-Gap Compliance**: Zero external cloud network requests or telemetry.
- [ ] **Docs & Invariants Updated**: Updated `docs/INVARIANTS.md` or `CHANGELOG.md` if applicable.

## Related Issues or Specs
<!-- E.g., Closes #123 or implements Spec section X -->
