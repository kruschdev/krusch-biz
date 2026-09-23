# Security & Air-Gap Policy for KruschBiz

## Sovereign Air-Gapped Topology
KruschBiz is engineered specifically for confidential enterprise transactions, corporate contracts, M&A deal rooms, and trade secrets.

### Security Invariants
1. **Loopback & Private Network Binding**:
   - Default port bindings are restricted strictly to loopback (`127.0.0.1:8086`, `127.0.0.1:8506`, `127.0.0.1:5436`).
   - The engine includes runtime assertions rejecting outbound non-private IP egress.
2. **Zero Telemetry & Cloud Egress**:
   - KruschBiz never transmits queries, embeddings, or contract contents to external third-party cloud LLM APIs.
   - All vector embeddings and LLM reasoning are processed locally via Ollama (`bge-large` and `qwen2.5:14b`).
3. **Strict Deal Room Partitioning**:
   - Client exhibits, redlines, and deal documents stored in `deal_evidence` are strictly isolated by `deal_id`.
   - Cross-account fact leakage is strictly 0.0%.
4. **Cryptographic Matter Hard Purge**:
   - Permanent deal purging via `DELETE /api/deals/{deal_id}/purge` cryptographically removes all deal facts, evidence embeddings, and grounding reports from disk and database, leaving only an anonymized audit receipt.
5. **KruschNexus Citation Sandboxing**:
   - Ingestion paths are constrained strictly within permitted directory allowlists (`ALLOWED_INGEST_DIRS`), preventing directory traversal attacks.

## Reporting Security Issues
Please report vulnerabilities privately via email to `kevin@krusch.dev`.
