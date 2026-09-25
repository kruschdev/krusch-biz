"""
src/backend/main.py
===================
FastAPI REST API application for KruschBiz Corporate Intelligence Engine.
Features:
  - Commercial contract, MSA, SLA, and policy search
  - Transaction deal matter management & hard deletion
  - Grounded executive memo synthesis with assertion auditing
  - Controlling-document graph resolver and contract conflict detection
  - KruschNexus / standalone document ingest adapter with MIME verification
  - Sovereign air-gap network boundaries and loopback enforcement
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from .compliance import (
    ContractVsStatuteRequest,
    ContractVsStatuteResponse,
    evaluate_contract_vs_statute,
)
from .config import settings, validate_security_invariants
from .db import (
    Agreement,
    AgreementRelation,
    AuditLog,
    Clause,
    CommercialClauseVector,
    CommercialGroundingReport,
    DealEvidence,
    DealMatter,
    ResolutionTraceRecord,
    SessionLocal,
    get_db,
    init_db,
    purge_deal_matter_transactional,
)
from .export import export_executive_memo_docx, export_executive_memo_markdown
from .ingest import (
    ingest_mock_data,
    ingest_uploaded_business_file,
)
from .rag import (
    generate_executive_brief,
    get_embedding,
    retrieve_clauses,
    retrieve_deal_evidence,
)
from .resolver import (
    detect_contract_conflicts,
    diff_agreements,
    resolve_controlling_clause,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s")
logger = logging.getLogger("kruschbiz.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables, vector extensions, security invariants, and seed fixtures on startup."""
    logger.info("Initializing KruschBiz corporate intelligence engine...")
    validate_security_invariants(settings)
    init_db()

    # Automatically seed mock fixtures if empty
    db = SessionLocal()
    try:
        count = db.query(CommercialClauseVector).count()
        if count == 0:
            logger.info("Database empty. Seeding initial corporate contract & policy fixtures...")
            ingest_mock_data(db)
    except Exception as e:
        logger.warning(f"Initial mock seeding skipped or failed ({e}).")
    finally:
        db.close()

    logger.info(f"KruschBiz ready. Listening on port {settings.BACKEND_PORT}.")
    yield
    logger.info("Shutting down KruschBiz.")


app = FastAPI(
    title="KruschBiz | Sovereign Corporate Intelligence Engine",
    description="Air-gapped enterprise contract and corporate policy graph with assertion-level grounding.",
    version="0.1.0",
    lifespan=lifespan
)

# Restrict CORS to authorized origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SimpleRateLimiter:
    """Thread-safe sliding window rate limiter."""
    def __init__(self, requests_per_minute: int = 30):
        self.rpm = requests_per_minute
        self.lock = threading.Lock()
        self.history: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            calls = self.history.get(key, [])
            calls = [t for t in calls if now - t < 60.0]
            if len(calls) >= self.rpm:
                return False
            calls.append(now)
            self.history[key] = calls
            return True


consult_rate_limiter = SimpleRateLimiter(requests_per_minute=30)
upload_rate_limiter = SimpleRateLimiter(requests_per_minute=20)


def verify_api_key(
    x_api_key: str | None = Header(None),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Enforce API key authentication and validate tenant binding to reject header spoofing."""
    if settings.API_KEY:
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key."
            )
        # Check tenant-scoped key format: 'tenant_id:key_secret'
        if ":" in x_api_key:
            bound_tenant, key_val = x_api_key.split(":", 1)
            if key_val.strip() != settings.API_KEY.strip():
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
            if bound_tenant.strip() != x_tenant_id.strip():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Tenant header spoofing rejected: API key is bound to tenant '{bound_tenant}', not '{x_tenant_id}'."
                )
        else:
            if x_api_key.strip() != settings.API_KEY.strip():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or missing API key."
                )
    return x_api_key


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class DealCreate(BaseModel):
    deal_code: str | None = Field(None, json_schema_extra={"example": "DEAL-2026-081"})
    company_name: str | None = Field(None, json_schema_extra={"example": "Acme Corp"})
    counterparty_name: str | None = Field(None, json_schema_extra={"example": "CloudScale AI LLC"})
    deal_type: str | None = Field(None, json_schema_extra={"example": "Vendor Procurement"})
    title: str = Field(..., json_schema_extra={"example": "Enterprise Cloud Hosting Services Agreement"})
    description: str | None = None
    context_facts: str = Field(..., json_schema_extra={"example": "Vendor submitted proposal with Net 30 payment terms and 99.9% uptime SLA."})


class DealUpdate(BaseModel):
    deal_code: str | None = None
    company_name: str | None = None
    counterparty_name: str | None = None
    deal_type: str | None = None
    title: str | None = None
    description: str | None = None
    context_facts: str | None = None
    status: str | None = None


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    deal_code: str | None
    company_name: str | None
    counterparty_name: str | None
    deal_type: str | None
    title: str
    description: str | None
    context_facts: str
    status: str
    created_at: datetime
    updated_at: datetime | None


class ClauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str = "org_default"
    organization: str
    counterparty: str | None = None
    agreement_type: str
    domain: str | None = None
    title: str | None = None
    section: str | None = None
    parent_section: str | None = None
    hierarchy_level: str = "clause"
    authority_class: str = "governing_agreement"
    effective_date: datetime | None = None
    expiration_date: datetime | None = None
    superseded: bool = False
    terminated: bool = False
    superseded_by: str | None = None
    content: str
    source_header: str | None = None
    topic: str | None = None
    tags: list[str] = []
    summary: str | None = None
    structured_slots: dict[str, Any] | None = None
    explanation: dict[str, Any] | None = None
    score: float | None = None
    vector_score: float | None = None
    lexical_score: float | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            return [str(t) for t in v]
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(t) for t in parsed]
            except Exception:
                pass
            return [t.strip() for t in v.split(",") if t.strip()]
        return []


class DealEvidenceItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deal_id: int
    tenant_id: str | None = None
    filename: str
    doc_type: str
    page_number: int | None = None
    section_locator: str | None = None
    chunk_index: int = 0
    content: str
    tags: list[str] = []
    summary: str | None = None
    topic: str | None = None
    similarity: float | None = 1.0
    created_at: str | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            return [str(t) for t in v]
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(t) for t in parsed]
            except Exception:
                pass
            return [t.strip() for t in v.split(",") if t.strip()]
        return []


class RelationCreate(BaseModel):
    source_agreement_id: int
    target_agreement_id: int
    relation_type: str
    clause_scope: str | None = "ALL"
    notes: str | None = None


class RelationUpdate(BaseModel):
    clause_scope: str | None = None
    relation_type: str | None = None
    target_agreement_id: int | None = None
    status: str | None = None
    effective_date: str | None = None


class ResolverRequest(BaseModel):
    counterparty: str = Field(..., description="Counterparty or vendor name")
    topic: str = Field(..., description="Canonical commercial topic, e.g. 'PAYMENT_TERMS'")
    as_of_date: str | None = Field(None, description="Optional ISO date (YYYY-MM-DD)")
    deal_id: int | None = Field(None, description="Optional associated deal matter ID")


class ConflictsRequest(BaseModel):
    counterparty: str = Field(..., description="Counterparty name")
    as_of_date: str | None = Field(None, description="Optional ISO date (YYYY-MM-DD)")
    deal_id: int | None = Field(None, description="Optional associated deal matter ID")


class WhatControlsExportRequest(BaseModel):
    counterparty: str = Field(..., description="Counterparty or vendor entity name")
    as_of_date: str = Field(..., description="Mandatory governing as-of date (YYYY-MM-DD)")
    topics: list[str] | None = Field(None, description="Optional list of topics to resolve")


class ConsultResponse(BaseModel):
    deal_id: int | None
    deal_title: str
    counterparty: str | None
    analysis: str
    grounding_stats: dict[str, Any]
    claims_audit: list[dict[str, Any]]
    retrieved_clauses: list[dict[str, Any]]
    controlling_clause_id: int | None = None
    amendment_trail: list[dict[str, Any]] = Field(default_factory=list)
    grounding_report_id: str | None = None
    review_required: bool = True
    model_name: str | None = None
    model_version: str | None = None
    prompt_hash: str | None = None


class ExportDocxRequest(BaseModel):
    deal_title: str
    deal_code: str | None = None
    counterparty: str | None = None
    deal_type: str | None = None
    brief_content: str | None = None
    analysis_text: str | None = None
    claims_records: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_clauses: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """System health check and diagnostic connectivity report."""
    db_ok = False
    try:
        db.execute(text("SELECT 1;"))
        db_ok = True
    except Exception as e:
        logger.error(f"Health check database ping failed: {e}")

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "kruschbiz-backend",
        "app_env": settings.APP_ENV,
        "database_connected": db_ok,
        "embedding_model": settings.OLLAMA_EMBED_MODEL,
        "llm_model": settings.OLLAMA_LLM_MODEL,
        "air_gapped": True,
        "ports": {
            "backend": settings.BACKEND_PORT,
            "frontend": settings.FRONTEND_PORT,
            "database": settings.DATABASE_PORT
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# --- Deal Matters CRUD ---

@app.post("/api/deals", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
def create_deal(
    deal_in: DealCreate,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Create a new corporate deal, vendor procurement review, or corporate transaction matter."""
    logger.info(f"Creating corporate deal: '{deal_in.title}' for tenant '{x_tenant_id}'...")
    deal = DealMatter(
        tenant_id=x_tenant_id,
        deal_code=deal_in.deal_code,
        company_name=deal_in.company_name,
        counterparty_name=deal_in.counterparty_name,
        deal_type=deal_in.deal_type,
        title=deal_in.title,
        description=deal_in.description,
        context_facts=deal_in.context_facts,
        status="active"
    )
    try:
        deal.embedding = get_embedding(f"{deal_in.title} {deal_in.context_facts}")
    except Exception as e:
        logger.warning(f"Could not generate deal embedding ({e}), proceeding without it.")

    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


@app.get("/api/deals", response_model=list[DealResponse])
def list_deals(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """List corporate deal matters for current tenant."""
    q = db.query(DealMatter).filter(
        DealMatter.tenant_id == x_tenant_id,
        DealMatter.is_deleted.is_(False)
    )
    if status_filter:
        q = q.filter(DealMatter.status == status_filter)
    return q.order_by(DealMatter.created_at.desc()).offset(offset).limit(limit).all()


@app.get("/api/deals/{deal_id}", response_model=DealResponse)
def get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Retrieve details of a corporate deal matter."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id,
        DealMatter.is_deleted.is_(False)
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")
    return deal


@app.patch("/api/deals/{deal_id}", response_model=DealResponse)
def update_deal(
    deal_id: int,
    deal_update: DealUpdate,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Update context, status, or details of a deal matter."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id,
        DealMatter.is_deleted.is_(False)
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")

    update_data = deal_update.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(deal, field, val)

    if "context_facts" in update_data or "title" in update_data:
        try:
            deal.embedding = get_embedding(f"{deal.title} {deal.context_facts}")
        except Exception:
            pass

    db.commit()
    db.refresh(deal)
    return deal


@app.delete("/api/deals/{deal_id}", status_code=status.HTTP_200_OK)
def soft_delete_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Soft delete a deal matter from active listings."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id,
        DealMatter.is_deleted.is_(False)
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")
    deal.is_deleted = True
    db.commit()
    return {"status": "success", "message": f"Deal #{deal_id} soft deleted."}


@app.delete("/api/deals/{deal_id}/hard-delete", status_code=status.HTTP_200_OK)
def hard_delete_deal(
    deal_id: int,
    confirm_deal_code: str | None = Query(None, description="Typed deal_code confirmation required for hard purge"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Hard purge: Permanently delete deal record, all associated evidence,
    reports, and invoices in a single atomic transaction.
    Requires typed confirmation matching the target deal_code.
    """
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")

    if deal.deal_code:
        if not confirm_deal_code or confirm_deal_code.strip() != deal.deal_code.strip():
            raise HTTPException(
                status_code=400,
                detail=f"Typed confirmation failed: 'confirm_deal_code' must match '{deal.deal_code}'."
            )

    purge_stats = purge_deal_matter_transactional(db, x_tenant_id, deal_id)

    actor_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest() if api_key else "anonymous"
    audit = AuditLog(
        tenant_id=x_tenant_id,
        action="hard_delete_deal",
        actor_key_hash=actor_hash,
        deal_id=deal_id,
        duration_ms=0,
        grounding_verdict="HARD_DELETED"
    )
    db.add(audit)
    db.commit()
    return {
        "status": "success",
        "message": f"Deal #{deal_id} permanently purged ({purge_stats['evidence']} evidence, {purge_stats['reports']} reports).",
        "purge_stats": purge_stats
    }


@app.delete("/api/deals/{deal_id}/purge", status_code=status.HTTP_200_OK, deprecated=True)
def legacy_purge_deal(
    deal_id: int,
    confirm_deal_code: str | None = Query(None),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Deprecated alias for hard_delete_deal."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")
    effective_confirm = confirm_deal_code or deal.deal_code
    return hard_delete_deal(
        deal_id=deal_id,
        confirm_deal_code=effective_confirm,
        db=db,
        api_key=api_key,
        x_tenant_id=x_tenant_id
    )


# --- Deal Room Evidence & Semantic Exhibits ---

@app.get("/api/deals/{deal_id}/evidence", response_model=list[DealEvidenceItem], tags=["Deals & Evidence"])
def get_deal_evidence(
    deal_id: int,
    q: str | None = Query(None, description="Semantic or keyword query within deal exhibits"),
    tag: str | None = Query(None, description="Filter by commercial semantic tag (e.g. 'payment-terms', 'net-30')"),
    topic: str | None = Query(None, description="Filter by canonical commercial topic (e.g. 'PAYMENT_TERMS')"),
    limit: int = Query(10, ge=1, le=100, description="Max evidence chunks to retrieve"),
    doc_type: str | None = Query(None, description="Optional doc_type filter (e.g. contract, redline, sla)"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Search deal room exhibits, vendor proposals, redlines, and commercial attachments
    strictly within the designated deal matter.
    Enriched with commercial semantic tags, 1-sentence micro-digests, and canonical topics.
    Prevents cross-deal and cross-tenant data contamination.
    """
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id,
        DealMatter.is_deleted.is_(False)
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")

    try:
        results = retrieve_deal_evidence(
            db=db,
            deal_id=deal_id,
            text_query=q,
            tag=tag,
            topic=topic,
            limit=limit,
            doc_type=doc_type,
            tenant_id=x_tenant_id
        )
        return [DealEvidenceItem(**r) for r in results]
    except Exception as e:
        logger.error(f"Error querying deal evidence: {e}")
        raise HTTPException(status_code=500, detail=f"Evidence retrieval error: {str(e)}")


@app.get("/api/deals/{deal_id}/evidence/tags", tags=["Deals & Evidence"])
def get_deal_evidence_tags(
    deal_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Return distinct commercial semantic tags and topics present in a deal's evidence corpus
    for faceted filtering and exploratory navigation.
    """
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id,
        DealMatter.is_deleted.is_(False)
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")

    rows = db.query(DealEvidence.tags, DealEvidence.topic).filter(
        DealEvidence.deal_id == deal_id,
        DealEvidence.tenant_id == x_tenant_id
    ).all()
    unique_tags = set()
    unique_topics = set()

    for tags_val, topic_val in rows:
        if topic_val:
            unique_topics.add(topic_val)
        if tags_val:
            try:
                parsed = json.loads(tags_val) if isinstance(tags_val, str) else list(tags_val)
                for t in parsed:
                    unique_tags.add(t)
            except Exception:
                for t in str(tags_val).split(","):
                    if t.strip():
                        unique_tags.add(t.strip())

    return {
        "deal_id": deal_id,
        "tags": sorted(list(unique_tags)),
        "topics": sorted(list(unique_topics)),
        "total_evidence_chunks": len(rows)
    }


# --- Clauses & Contract Search ---

@app.get("/api/clauses", response_model=list[ClauseResponse])
def search_clauses(
    q: str | None = Query(None, description="Natural language search or clause keywords"),
    organization: str | None = Query(None),
    agreement_type: str | None = Query(None),
    domain: str | None = Query(None),
    topic: str | None = Query(None, description="Filter by canonical commercial topic"),
    tag: str | None = Query(None, description="Filter by commercial semantic tag"),
    limit: int = Query(5, ge=1, le=50),
    offset: int = Query(0, ge=0),
    exclude_superseded: bool = Query(True),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Search commercial clauses across the corporate agreement graph.
    Uses hybrid dense ANN + lexical search with authority hierarchy weighting.
    """
    if q and q.strip():
        results = retrieve_clauses(
            db=db,
            query=q,
            limit=limit,
            offset=offset,
            organization=organization,
            agreement_type=agreement_type,
            domain=domain,
            exclude_superseded=exclude_superseded,
            topic=topic,
            tag=tag,
            tenant_id=x_tenant_id
        )
        return results

    query_obj = db.query(CommercialClauseVector).filter(
        CommercialClauseVector.tenant_id == x_tenant_id,
        CommercialClauseVector.superseded.is_(False),
        CommercialClauseVector.terminated.is_(False)
    )
    if organization:
        query_obj = query_obj.filter(CommercialClauseVector.organization.ilike(f"%{organization}%"))
    if agreement_type:
        query_obj = query_obj.filter(CommercialClauseVector.agreement_type.ilike(f"%{agreement_type}%"))
    if domain:
        query_obj = query_obj.filter(CommercialClauseVector.domain.ilike(f"%{domain}%"))
    if topic:
        query_obj = query_obj.filter(CommercialClauseVector.topic.ilike(f"%{topic}%"))
    if tag:
        query_obj = query_obj.filter(CommercialClauseVector.tags.ilike(f"%{tag}%"))

    items = query_obj.order_by(
        CommercialClauseVector.effective_date.desc().nullslast(),
        CommercialClauseVector.id.desc()
    ).offset(offset).limit(limit).all()
    return items


# --- Controlling Document Resolver & Conflicts ---

@app.post("/api/resolver/controlling")
def resolve_controlling_post(
    body: ResolverRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    POST resolver endpoint: Walk the agreement relation graph (AMENDS, SUPERSEDES)
    to resolve which clause governs the specified topic as of a specific date.
    """
    parsed_date = None
    if body.as_of_date:
        try:
            parsed_date = datetime.fromisoformat(body.as_of_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD).")

    result = resolve_controlling_clause(
        db=db,
        tenant_id=x_tenant_id,
        counterparty=body.counterparty,
        topic=body.topic,
        as_of_date=parsed_date
    )
    return result


@app.post("/api/resolver/conflicts")
def get_contract_conflicts_post(
    body: ConflictsRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    POST conflicts endpoint: Detect conflicting slot values across concurrently active instruments.
    """
    parsed_date = None
    if body.as_of_date:
        try:
            parsed_date = datetime.fromisoformat(body.as_of_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD).")

    conflicts = detect_contract_conflicts(
        db=db,
        tenant_id=x_tenant_id,
        counterparty=body.counterparty,
        as_of_date=parsed_date
    )
    return {"counterparty": body.counterparty, "conflicts": conflicts, "total_conflicts": len(conflicts)}


@app.post("/conflicts/contract-vs-statute", response_model=ContractVsStatuteResponse)
@app.post("/api/conflicts/contract-vs-statute", response_model=ContractVsStatuteResponse)
def check_contract_vs_statute_conflicts(
    body: ContractVsStatuteRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    The Join Endpoint: Evaluates controlling commercial contract terms (KruschBiz DAG)
    against mandatory statutory ceilings and floors (KruschLaw Precedence Graph).
    """
    try:
        return evaluate_contract_vs_statute(
            db_biz=db,
            request=body,
            tenant_id=x_tenant_id
        )
    except ValueError as val_err:
        raise HTTPException(status_code=422, detail=str(val_err))
    except Exception as exc:
        logger.error(f"Error in evaluate_contract_vs_statute: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Compliance evaluation failed: {exc}")


@app.get("/api/resolver/controlling-clause")
def get_controlling_clause(
    counterparty: str = Query(..., description="Counterparty name"),
    topic: str = Query(..., description="Canonical commercial topic"),
    as_of_date: str | None = Query(None, description="ISO format date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Walk the agreement relation graph (AMENDS, SUPERSEDES) to resolve which clause
    governs the specified topic as of a specific date.
    """
    parsed_date = None
    if as_of_date:
        try:
            parsed_date = datetime.fromisoformat(as_of_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD).")

    result = resolve_controlling_clause(
        db=db,
        tenant_id=x_tenant_id,
        counterparty=counterparty,
        topic=topic,
        as_of_date=parsed_date
    )
    return result


@app.get("/api/resolver/conflicts")
def get_contract_conflicts(
    counterparty: str = Query(..., description="Counterparty name"),
    as_of_date: str | None = Query(None, description="ISO format date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Detect conflicting slot values (e.g. Net 30 vs Net 45) across concurrently active instruments.
    """
    parsed_date = None
    if as_of_date:
        try:
            parsed_date = datetime.fromisoformat(as_of_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD).")

    conflicts = detect_contract_conflicts(
        db=db,
        tenant_id=x_tenant_id,
        counterparty=counterparty,
        as_of_date=parsed_date
    )
    return {"counterparty": counterparty, "conflicts": conflicts, "total_conflicts": len(conflicts)}


@app.get("/api/agreements/conflicts")
def get_agreements_conflicts(
    counterparty: str = Query(..., description="Counterparty name"),
    as_of_date: str | None = Query(None, description="ISO format date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Pre-generation conflict report: Scan portfolio for active commercial conflicts."""
    return get_contract_conflicts(counterparty, as_of_date, db, api_key, x_tenant_id)


@app.post("/api/resolver/what-controls-export")
def export_what_controls_endpoint(
    body: WhatControlsExportRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Generate an authoritative 1-page 'What Controls as of DATE' General Counsel memorandum
    and JSON audit trail with amendment lineage.
    """
    from .export import generate_what_controls_export
    try:
        parsed_date = datetime.fromisoformat(body.as_of_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD).")

    topics = body.topics
    if not topics:
        agreements = db.query(Agreement).filter(
            Agreement.tenant_id == x_tenant_id,
            Agreement.counterparty.ilike(body.counterparty.strip())
        ).all()
        ag_ids = [ag.id for ag in agreements]
        distinct_topics = db.query(Clause.topic).filter(
            Clause.tenant_id == x_tenant_id,
            Clause.agreement_id.in_(ag_ids),
            Clause.is_active.is_(True),
            Clause.topic != "GENERAL_COMMERCIAL"
        ).distinct().all()
        topics = [t[0] for t in distinct_topics if t[0]]
        if not topics:
            topics = ["PAYMENT_TERMS", "LIMITATION_OF_LIABILITY", "SLA_UPTIME", "INDEMNIFICATION"]

    resolutions = []
    for top in topics:
        res = resolve_controlling_clause(
            db=db,
            tenant_id=x_tenant_id,
            counterparty=body.counterparty,
            topic=top,
            as_of_date=parsed_date
        )
        res["topic"] = top
        resolutions.append(res)

    return generate_what_controls_export(
        counterparty=body.counterparty,
        as_of_date=body.as_of_date,
        resolutions=resolutions,
        tenant_id=x_tenant_id
    )


@app.get("/api/resolution-traces")
def list_resolution_traces(
    counterparty: str | None = Query(None, description="Filter by counterparty"),
    topic: str | None = Query(None, description="Filter by canonical topic"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Query immutable audit log of commercial precedence graph walks."""
    query = db.query(ResolutionTraceRecord).filter(ResolutionTraceRecord.tenant_id == x_tenant_id)
    if counterparty:
        query = query.filter(ResolutionTraceRecord.counterparty == counterparty)
    if topic:
        query = query.filter(ResolutionTraceRecord.topic == topic)
    records = query.order_by(ResolutionTraceRecord.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "tenant_id": r.tenant_id,
            "counterparty": r.counterparty,
            "topic": r.topic,
            "as_of_date": r.as_of_date,
            "status": r.status,
            "controlling_agreement_id": r.controlling_agreement_id,
            "controlling_clause_id": r.controlling_clause_id,
            "confidence": r.confidence,
            "resolution_rationale": r.resolution_rationale,
            "trace_payload": r.trace_payload,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in records
    ]


@app.get("/api/resolver/diff")
def diff_contract_instruments(
    agreement_a_id: int = Query(..., description="Base Agreement ID (e.g. 2021 MSA)"),
    agreement_b_id: int = Query(..., description="Target Agreement ID (e.g. 2025 MSA or Amendment)"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Diff two legal instruments side-by-side:
    Compares aligned clauses, extracts text diffs, and highlights diverging structured slots.
    """
    diff_report = diff_agreements(
        db=db,
        agreement_a_id=agreement_a_id,
        agreement_b_id=agreement_b_id,
        tenant_id=x_tenant_id
    )
    if diff_report.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=diff_report["message"])
    return diff_report


@app.get("/api/agreements")
def list_agreements(
    counterparty: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """List legal instruments / agreements for the active tenant."""
    query = db.query(Agreement).filter(Agreement.tenant_id == x_tenant_id)
    if counterparty:
        query = query.filter(Agreement.counterparty.ilike(f"%{counterparty}%"))
    if status_filter:
        query = query.filter(Agreement.status == status_filter)
    agreements = query.order_by(Agreement.effective_date.desc().nullslast()).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "instrument_type": a.instrument_type,
            "counterparty": a.counterparty,
            "status": a.status,
            "effective_date": a.effective_date.isoformat() if a.effective_date else None,
            "clauses_count": len(a.clauses) if a.clauses else 0
        }
        for a in agreements
    ]


# --- Agreement Relations CRUD ---

@app.get("/api/relations")
def list_relations(
    status_filter: str | None = Query(None, alias="status"),
    relation_type: str | None = Query(None),
    agreement_id: int | None = Query(None),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """List agreement relations (AMENDS, SUPERSEDES, SCHEDULE_OF, INCORPORATES) for the tenant."""
    query = db.query(AgreementRelation).filter(AgreementRelation.tenant_id == x_tenant_id)
    if relation_type:
        query = query.filter(AgreementRelation.relation_type == relation_type)
    if agreement_id:
        query = query.filter(
            or_(
                AgreementRelation.source_agreement_id == agreement_id,
                AgreementRelation.target_agreement_id == agreement_id
            )
        )
    relations = query.order_by(AgreementRelation.created_at.desc()).all()

    results = []
    for r in relations:
        parsed_notes = {}
        if r.notes:
            try:
                parsed_notes = json.loads(r.notes)
            except Exception:
                pass
        rel_status = parsed_notes.get("status", "confirmed")
        if status_filter and rel_status != status_filter:
            continue

        src_ag = db.query(Agreement.title).filter(Agreement.id == r.source_agreement_id).first()
        tgt_ag = db.query(Agreement.title).filter(Agreement.id == r.target_agreement_id).first()

        results.append({
            "id": r.id,
            "tenant_id": r.tenant_id,
            "source_agreement_id": r.source_agreement_id,
            "source_title": src_ag[0] if src_ag else f"Agreement #{r.source_agreement_id}",
            "target_agreement_id": r.target_agreement_id,
            "target_title": tgt_ag[0] if tgt_ag else f"Agreement #{r.target_agreement_id}",
            "relation_type": r.relation_type,
            "clause_scope": r.clause_scope,
            "effective_date": r.effective_date.isoformat() if r.effective_date else None,
            "status": rel_status,
            "confidence": parsed_notes.get("confidence", 1.0),
            "source_excerpt": parsed_notes.get("source_excerpt"),
            "source_span": r.source_span or r.span or parsed_notes.get("source_excerpt"),
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return results


@app.post("/api/relations", status_code=status.HTTP_201_CREATED)
def create_relation(
    rel_in: RelationCreate,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Explicitly create an agreement relation edge."""
    rel_status = "confirmed"
    if rel_in.notes:
        try:
            parsed = json.loads(rel_in.notes)
            rel_status = parsed.get("status", "confirmed")
        except Exception:
            pass

    rel = AgreementRelation(
        tenant_id=x_tenant_id,
        source_agreement_id=rel_in.source_agreement_id,
        target_agreement_id=rel_in.target_agreement_id,
        relation_type=rel_in.relation_type,
        clause_scope=rel_in.clause_scope or "ALL",
        status=rel_status,
        notes=rel_in.notes or json.dumps({"status": rel_status})
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return {"id": rel.id, "status": "created"}


@app.patch("/api/relations/{relation_id}/confirm")
@app.post("/api/relations/{relation_id}/confirm")
def confirm_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Human review confirmation of a proposed relation edge."""
    rel = db.query(AgreementRelation).filter(
        AgreementRelation.id == relation_id,
        AgreementRelation.tenant_id == x_tenant_id
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation edge not found.")

    rel.status = "confirmed"
    parsed_notes = {}
    if rel.notes:
        try:
            parsed_notes = json.loads(rel.notes)
        except Exception:
            pass
    parsed_notes["status"] = "confirmed"
    parsed_notes["confirmed_at"] = datetime.now(timezone.utc).isoformat()
    rel.notes = json.dumps(parsed_notes)
    db.commit()
    db.refresh(rel)
    return {"id": rel.id, "status": "confirmed"}


@app.patch("/api/relations/{relation_id}/reject")
@app.post("/api/relations/{relation_id}/reject")
def reject_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Human review rejection of a proposed relation edge."""
    rel = db.query(AgreementRelation).filter(
        AgreementRelation.id == relation_id,
        AgreementRelation.tenant_id == x_tenant_id
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation edge not found.")

    rel.status = "rejected"
    parsed_notes = {}
    if rel.notes:
        try:
            parsed_notes = json.loads(rel.notes)
        except Exception:
            pass
    parsed_notes["status"] = "rejected"
    parsed_notes["rejected_at"] = datetime.now(timezone.utc).isoformat()
    rel.notes = json.dumps(parsed_notes)
    db.commit()
    db.refresh(rel)
    return {"id": rel.id, "status": "rejected"}


@app.patch("/api/relations/{relation_id}")
def update_relation(
    relation_id: int,
    rel_update: RelationUpdate,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Edit relation properties (clause_scope, relation_type, target_agreement_id, status)."""
    rel = db.query(AgreementRelation).filter(
        AgreementRelation.id == relation_id,
        AgreementRelation.tenant_id == x_tenant_id
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation edge not found.")

    if rel_update.clause_scope is not None:
        rel.clause_scope = rel_update.clause_scope
    if rel_update.relation_type is not None:
        rel.relation_type = rel_update.relation_type
    if rel_update.target_agreement_id is not None:
        rel.target_agreement_id = rel_update.target_agreement_id
    if rel_update.effective_date is not None:
        try:
            rel.effective_date = datetime.fromisoformat(rel_update.effective_date)
        except Exception:
            pass
    if rel_update.status is not None:
        rel.status = rel_update.status

    parsed_notes = {}
    if rel.notes:
        try:
            parsed_notes = json.loads(rel.notes)
        except Exception:
            pass
    if rel_update.status is not None:
        parsed_notes["status"] = rel_update.status
    parsed_notes["edited_at"] = datetime.now(timezone.utc).isoformat()
    rel.notes = json.dumps(parsed_notes)

    db.commit()
    db.refresh(rel)
    return {
        "id": rel.id,
        "status": rel.status,
        "clause_scope": rel.clause_scope,
        "relation_type": rel.relation_type,
        "target_agreement_id": rel.target_agreement_id,
        "effective_date": rel.effective_date.isoformat() if rel.effective_date else None
    }


@app.delete("/api/relations/{relation_id}")
def delete_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Remove or reject a relation edge."""
    rel = db.query(AgreementRelation).filter(
        AgreementRelation.id == relation_id,
        AgreementRelation.tenant_id == x_tenant_id
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation edge not found.")
    db.delete(rel)
    db.commit()
    return {"id": relation_id, "status": "deleted"}


# --- Adversarial Multi-Document Evaluation Benchmark ---

@app.get("/api/evaluation/adversarial")
def get_adversarial_evaluation(
    force_rerun: bool = Query(False, description="Force re-execution of adversarial corpus"),
    api_key: str | None = Depends(verify_api_key)
):
    """
    Retrieve empirical scorecard for the 7 adversarial multi-document families:
    1. Relation Extraction F1
    2. Controlling-Clause Accuracy As-Of Date
    3. Slot Exact-Match Accuracy
    4. Proposition Classification Accuracy
    """
    results_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data/eval/adversarial_eval_results.json"
    )
    if not force_rerun and os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed reading cached eval results: {e}")

    try:
        from scripts.eval_adversarial_corpus import run_adversarial_eval
        return run_adversarial_eval(output_json_path=results_path, verbose=False)
    except Exception as exc:
        logger.error(f"Failed running adversarial evaluation: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Adversarial evaluation failed: {exc}")



# --- Corporate Intelligence Consult & Memo Generation ---

@app.get("/api/consult", response_model=ConsultResponse)
def consult_deal(
    deal_id: int | None = Query(None, description="Deal ID to consult"),
    query: str | None = Query(None, description="Ad-hoc transaction facts or inquiry"),
    limit: int = Query(5, ge=1, le=10),
    organization: str | None = Query(None),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Synthesize an executive commercial brief grounded in the contract graph.
    Performs assertion-level verification, detects divergent terms, and logs an audit record.
    """
    rate_key = f"{x_tenant_id}:consult"
    if not consult_rate_limiter.check(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded on /api/consult (maximum 30 requests per minute)."
        )

    start_time = time.time()
    deal = None
    deal_title = "Ad-Hoc Commercial Inquiry"
    context_facts = query or ""
    counterparty = None
    deal_type = None

    if deal_id is not None:
        deal = db.query(DealMatter).filter(
            DealMatter.id == deal_id,
            DealMatter.tenant_id == x_tenant_id,
            DealMatter.is_deleted.is_(False)
        ).first()
        if not deal:
            raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")
        deal_title = deal.title
        context_facts = f"{deal.title}\n{deal.context_facts}"
        if query:
            context_facts += f"\nSpecific Inquiry: {query}"
        counterparty = deal.counterparty_name
        deal_type = deal.deal_type

    if not context_facts.strip():
        raise HTTPException(status_code=400, detail="Either 'deal_id' or 'query' must provide transaction facts.")

    # 1. Hybrid Retrieval of governing authorities
    search_query = f"{deal_title} {context_facts}"
    clauses = retrieve_clauses(
        db=db,
        query=search_query,
        limit=limit,
        organization=organization or (deal.company_name if deal else None),
        exclude_superseded=True,
        tenant_id=x_tenant_id
    )

    # 2. Generate grounded brief with refusal checks
    analysis_text, grounding_stats, claims_records = generate_executive_brief(
        deal_title=deal_title,
        context_facts=context_facts,
        clauses=clauses,
        counterparty=counterparty,
        deal_type=deal_type
    )

    # 3. Persist Grounding Report
    rep_id = None
    if deal_id is not None:
        rep = CommercialGroundingReport(
            tenant_id=x_tenant_id,
            deal_id=deal_id,
            total_claims=grounding_stats.get("total_claims", 0),
            supported_claims=grounding_stats.get("supported_claims", 0),
            unsupported_claims=grounding_stats.get("unsupported_claims", 0),
            invented_clauses=grounding_stats.get("invented_clauses", 0),
            divergent_terms=grounding_stats.get("divergent_terms", 0),
            superseded_terms=grounding_stats.get("superseded_terms", 0),
            pass_rate=grounding_stats.get("pass_rate", 100.0),
            claims_json=json.dumps(claims_records),
            advisory_markdown=analysis_text
        )
        db.add(rep)
        db.flush()
        rep_id = rep.id

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 4. Audit Log
    clause_ids = ",".join(str(c["id"]) for c in clauses)
    verdict = "PASS" if grounding_stats.get("unsupported_claims", 0) == 0 else "WARNING"
    actor_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest() if api_key else "anonymous"
    prompt_hash = hashlib.sha256(f"{deal_title}|{context_facts}".encode("utf-8")).hexdigest()[:16]
    controlling_id = clauses[0]["id"] if clauses else None

    audit = AuditLog(
        tenant_id=x_tenant_id,
        action="consult",
        actor_key_hash=actor_hash,
        deal_id=deal_id,
        retrieved_clause_ids=clause_ids,
        model_name=settings.OLLAMA_LLM_MODEL,
        model_version="qwen2.5-coder:7b",
        prompt_hash=prompt_hash,
        grounding_verdict=verdict,
        duration_ms=elapsed_ms
    )
    db.add(audit)
    db.commit()

    return ConsultResponse(
        deal_id=deal_id,
        deal_title=deal_title,
        counterparty=counterparty,
        analysis=analysis_text,
        grounding_stats=grounding_stats,
        claims_audit=claims_records,
        retrieved_clauses=clauses,
        controlling_clause_id=controlling_id,
        amendment_trail=[],
        grounding_report_id=rep_id,
        review_required=True,
        model_name=settings.OLLAMA_LLM_MODEL,
        model_version="qwen2.5-coder:7b",
        prompt_hash=prompt_hash
    )


# --- Executive Memorandum Document Exporters ---

@app.post("/api/consult/export/docx")
def export_deal_docx(
    req: ExportDocxRequest,
    api_key: str | None = Depends(verify_api_key)
):
    """Generate and download a high-prestige executive memorandum (.docx)."""
    content_text = req.brief_content or req.analysis_text or ""
    docx_bytes = export_executive_memo_docx(
        brief_content=content_text,
        deal_title=req.deal_title,
        deal_code=req.deal_code,
        counterparty=req.counterparty,
        deal_type=req.deal_type,
        claims_records=req.claims_records,
        retrieved_clauses=req.retrieved_clauses
    )
    filename = f"Executive_Memo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/consult/export/md")
def export_deal_markdown(
    req: ExportDocxRequest,
    api_key: str | None = Depends(verify_api_key)
):
    """Generate and download a clean executive memorandum in Markdown (.md)."""
    content_text = req.brief_content or req.analysis_text or ""
    md_content = export_executive_memo_markdown(
        brief_content=content_text,
        deal_title=req.deal_title,
        deal_code=req.deal_code,
        counterparty=req.counterparty,
        deal_type=req.deal_type,
        claims_records=req.claims_records,
        retrieved_clauses=req.retrieved_clauses
    )
    filename = f"Executive_Memo_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# --- Document Ingestion Upload ---

@app.post("/api/ingest/upload", status_code=status.HTTP_200_OK)
def upload_business_document(
    file: UploadFile = File(...),
    deal_id: int | None = Form(None),
    doc_type: str = Form("contract"),
    organization: str = Form("Acme Corp"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Secure file upload endpoint for business contracts, SLAs, DPAs, and exhibits.
    Applies pre-spool MIME verification, rate limiting, chunk DOS limits, and structured slot extraction.
    """
    rate_key = f"{x_tenant_id}:upload"
    if not upload_rate_limiter.check(rate_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded on /api/ingest/upload (maximum 20 uploads per minute)."
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename in upload.")

    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    allowed_exts = {".md", ".markdown", ".txt", ".docx", ".pdf"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported document format: invalid file extension '{ext}'. Allowed: {', '.join(sorted(allowed_exts))}"
        )

    # Inspect first 512 bytes before spooling to disk
    header_bytes = file.file.read(512)
    file.file.seek(0)
    if ext == ".pdf" and not header_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="File signature mismatch: expected %PDF- header for .pdf extension.")
    if ext in (".docx", ".doc") and not (header_bytes.startswith(b"PK\x03\x04") or header_bytes.startswith(b"\xd0\xcf\x11\xe0")):
        raise HTTPException(status_code=400, detail="File signature mismatch: expected PK or compound document header for .docx extension.")
    if header_bytes.startswith(b"MZ") or header_bytes.startswith(b"\x7fELF") or header_bytes.startswith(b"\xfe\xed\xfa\xce"):
        raise HTTPException(status_code=400, detail="Disguised executable binary payload rejected.")

    logger.info(f"Receiving verified file upload '{file.filename}' for deal #{deal_id} (tenant: {x_tenant_id})...")
    try:
        report = ingest_uploaded_business_file(
            file=file,
            deal_id=deal_id,
            doc_type=doc_type,
            organization=organization,
            tenant_id=x_tenant_id,
            db=db
        )
        return report
    except ValueError as ve:
        logger.warning(f"Invalid uploaded document request: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Unexpected file ingestion error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@app.post("/api/ingest/seed")
def seed_fixtures(
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Seed demo contracts, agreements, and relation graph for the tenant."""
    report = ingest_mock_data(db, tenant_id=x_tenant_id)
    return report
