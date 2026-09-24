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

import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings, validate_security_invariants
from .db import (
    Agreement,
    AuditLog,
    CommercialClauseVector,
    CommercialGroundingReport,
    DealEvidence,
    DealMatter,
    SessionLocal,
    get_db,
    init_db,
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

from .business_router import router as business_router

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

# Mount Business Operations & Commercial Utilities Router
app.include_router(
    business_router,
    prefix="/api/business",
    tags=["Business Operations & Commercial Utilities"]
)


def verify_api_key(x_api_key: str | None = Header(None)):
    """Enforce API key authentication if configured in settings."""
    if settings.API_KEY:
        if not x_api_key or x_api_key.strip() != settings.API_KEY.strip():
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


class ConsultResponse(BaseModel):
    deal_id: int | None
    deal_title: str
    counterparty: str | None
    analysis: str
    grounding_stats: dict[str, Any]
    claims_audit: list[dict[str, Any]]
    retrieved_clauses: list[dict[str, Any]]


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
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """
    Hard delete: Permanently delete deal record, all associated evidence,
    and grounding reports, recording an immutable audit entry.
    """
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == x_tenant_id
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")

    ev_count = db.query(DealEvidence).filter(
        DealEvidence.deal_id == deal_id,
        DealEvidence.tenant_id == x_tenant_id
    ).delete()
    rep_count = db.query(CommercialGroundingReport).filter(
        CommercialGroundingReport.deal_id == deal_id,
        CommercialGroundingReport.tenant_id == x_tenant_id
    ).delete()
    db.delete(deal)

    audit = AuditLog(
        tenant_id=x_tenant_id,
        action="hard_delete_deal",
        deal_id=deal_id,
        duration_ms=0,
        grounding_verdict="HARD_DELETED"
    )
    db.add(audit)
    db.commit()
    return {
        "status": "success",
        "message": f"Deal #{deal_id} permanently deleted and permanently purged ({ev_count} evidence records, {rep_count} grounding reports)."
    }


@app.delete("/api/deals/{deal_id}/purge", status_code=status.HTTP_200_OK, deprecated=True)
def legacy_purge_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key),
    x_tenant_id: str = Header("org_default", alias="X-Tenant-ID")
):
    """Deprecated alias for hard_delete_deal."""
    return hard_delete_deal(deal_id=deal_id, db=db, api_key=api_key, x_tenant_id=x_tenant_id)


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

    items = query_obj.order_by(CommercialClauseVector.id.asc()).offset(offset).limit(limit).all()
    return items


# --- Controlling Document Resolver & Conflicts ---

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

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 4. Audit Log
    clause_ids = ",".join(str(c["id"]) for c in clauses)
    verdict = "PASS" if grounding_stats.get("unsupported_claims", 0) == 0 else "WARNING"
    audit = AuditLog(
        tenant_id=x_tenant_id,
        action="consult",
        deal_id=deal_id,
        retrieved_clause_ids=clause_ids,
        model_name=settings.OLLAMA_LLM_MODEL,
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
        retrieved_clauses=clauses
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
    Applies MIME verification, chunk DOS limits, and structured slot extraction.
    """
    logger.info(f"Receiving file upload '{file.filename}' for deal #{deal_id} (tenant: {x_tenant_id})...")
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
