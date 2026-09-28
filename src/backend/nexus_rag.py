"""
src/backend/nexus_rag.py
========================
KruschNexus RAG retrieval adapter for KruschBiz.
Provides zero vendor lock-in retrieval delegation to NexusClient:
- backend="local": PostgreSQL pgvector + Ollama bge-large
- backend="wondersearch": Wondersearch Cloud Drives (gated by ALLOW_CLOUD=1)
Preserves INV-11 Physical Citation Coordinates (bbox, page_number, char spans).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from .config import settings

logger = logging.getLogger("kruschbiz.nexus_rag")

_NEXUS_AVAILABLE = False
_NEXUS_CLIENT = None


def _resolve_nexus():
    global _NEXUS_AVAILABLE
    try:
        import krusch_nexus  # noqa: F401
        _NEXUS_AVAILABLE = True
    except ImportError:
        candidate_paths = [
            getattr(settings, "KRUSCH_NEXUS_PATH", None),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "krusch-nexus", "src"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "krusch-nexus", "src"),
            "/nexus/src",
            os.path.expanduser("~/homelab/projects/krusch-nexus/src"),
        ]
        for p in candidate_paths:
            if p and os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)
                break
        try:
            import krusch_nexus  # noqa: F401
            _NEXUS_AVAILABLE = True
        except ImportError:
            _NEXUS_AVAILABLE = False


_resolve_nexus()


def is_nexus_available() -> bool:
    return _NEXUS_AVAILABLE


def get_nexus_client() -> Any:
    global _NEXUS_CLIENT
    if _NEXUS_CLIENT is not None:
        return _NEXUS_CLIENT
    if not is_nexus_available():
        return None
    from krusch_nexus import NexusClient, NexusConfig

    backend = os.getenv("NEXUS_BACKEND", "local").lower()
    allow_cloud = getattr(settings, "ALLOW_CLOUD", False) or os.getenv("ALLOW_CLOUD", "0") in ("1", "true", "True")
    if backend == "wondersearch" and not allow_cloud:
        from krusch_nexus.exceptions import AirGapViolationError
        raise AirGapViolationError(
            "Security Violation: KruschBiz refuses connection to cloud Wondersearch backend without ALLOW_CLOUD=1."
        )

    cfg = NexusConfig.from_env()
    _NEXUS_CLIENT = NexusClient(config=cfg)
    return _NEXUS_CLIENT


def search_clauses_nexus(
    query_text: str,
    topic: str | None = None,
    limit: int = 5,
    organization: str | None = None,
    agreement_type: str | None = None,
    workspace: str = "biz_playbooks"
) -> list[dict[str, Any]]:
    """Retrieve contract clauses using KruschNexus / Wondersearch provider."""
    client = get_nexus_client()
    if not client:
        return []

    filters = {}
    if topic:
        filters["topic"] = topic
    if organization:
        filters["organization"] = organization
    if agreement_type:
        filters["agreement_type"] = agreement_type

    hits = client.search(
        query=query_text,
        workspace=workspace,
        limit=limit,
        filters=filters if filters else None
    )

    results = []
    for hit in hits:
        meta = hit.score_vector or {}
        section_name = hit.locator or hit.header or "Section 1.0"
        title_name = hit.citation or hit.header or "Standard Clause"
        results.append({
            "id": hit.chunk_id,
            "organization": meta.get("organization", organization or "Standard"),
            "counterparty": meta.get("counterparty"),
            "agreement_type": meta.get("agreement_type", agreement_type or "Master Services Agreement"),
            "domain": meta.get("domain", "Procurement & Invoicing"),
            "title": title_name,
            "section": section_name,
            "parent_section": meta.get("parent_section"),
            "hierarchy_level": meta.get("hierarchy_level", 1),
            "definitions_ref": meta.get("definitions_ref"),
            "exceptions_ref": meta.get("exceptions_ref"),
            "authority_class": meta.get("authority_class", "governing_agreement"),
            "effective_date": meta.get("effective_date"),
            "superseded": meta.get("superseded", False),
            "terminated": meta.get("terminated", False),
            "superseded_by": meta.get("superseded_by"),
            "source_url": meta.get("source_url"),
            "content": hit.text,
            "structured_slots": meta.get("structured_slots", {}),
            "topic": meta.get("topic", topic or "General"),
            "tags": meta.get("tags", []),
            "summary": meta.get("summary"),
            "page_number": hit.page_number,
            "printed_page": hit.printed_page,
            "bbox": hit.bbox,
            "char_start": hit.char_start,
            "char_end": hit.char_end,
            "extra_metadata": meta.get("extra_metadata"),
            "score": float(hit.score),
            "similarity": float(hit.score),
            "authority_weight": 1.0,
            "vector_similarity": float(hit.score),
            "bm25_score": float(hit.score),
            "structured_match": False
        })
    return results


def search_deal_evidence_nexus(
    deal_id: int,
    text_query: str | None = None,
    topic: str | None = None,
    limit: int = 10,
    doc_type: str | None = None,
    tenant_id: str = "org_default"
) -> list[dict[str, Any]]:
    """Retrieve deal room exhibits and proposals using KruschNexus / Wondersearch provider."""
    client = get_nexus_client()
    if not client:
        return []

    workspace = f"deal_{deal_id}"
    filters = {"tenant_id": tenant_id}
    if doc_type:
        filters["doc_type"] = doc_type
    if topic:
        filters["topic"] = topic

    hits = client.search(
        query=text_query or "*",
        workspace=workspace,
        limit=limit,
        filters=filters
    )

    results = []
    for hit in hits:
        meta = hit.score_vector or {}
        tags_list = meta.get("tags", [])
        if isinstance(tags_list, str):
            tags_list = [t.strip() for t in tags_list.split(",") if t.strip()]

        results.append({
            "id": hit.chunk_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "filename": hit.filename or meta.get("filename", "contract.pdf"),
            "doc_type": hit.doc_type or meta.get("doc_type", doc_type or "proposal"),
            "page_number": hit.page_number,
            "printed_page": hit.printed_page,
            "bbox": hit.bbox,
            "char_start": hit.char_start,
            "char_end": hit.char_end,
            "extra_metadata": meta.get("extra_metadata"),
            "section_locator": hit.locator or hit.header or "General",
            "chunk_index": hit.chunk_index or 0,
            "content": hit.text,
            "tags": tags_list,
            "summary": meta.get("summary"),
            "topic": meta.get("topic", topic or "General"),
            "score": round(float(hit.score), 4),
            "similarity": round(float(hit.score), 4),
            "created_at": meta.get("created_at")
        })
    return results
