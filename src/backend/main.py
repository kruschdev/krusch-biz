import hashlib
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .db import (
    AuditLog,
    CommercialClauseVector,
    CommercialGroundingReport,
    DealEvidence,
    DealMatter,
    SessionLocal,
    init_db,
)
from .export import generate_brief_docx, generate_brief_markdown
from .ingest import ingest_business_document, ingest_mock_data, ingest_uploaded_business_file
from .rag import generate_executive_brief, get_embedding, retrieve_clauses

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (kruschbiz.api) %(message)s"
)
logger = logging.getLogger("kruschbiz.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and verify local air-gapped security bindings."""
    logger.info("Initializing KruschBiz Sovereign Corporate Intelligence Engine...")
    init_db()
    yield
    logger.info("Shutting down KruschBiz.")


app = FastAPI(
    title="KruschBiz | Sovereign Corporate Intelligence Engine",
    description="Air-gapped enterprise contract and corporate policy graph with assertion-level grounding.",
    version="0.3.0",
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    deal_code: str | None = Field(None, example="DEAL-2026-081")
    company_name: str | None = Field(None, example="Acme Corp")
    counterparty_name: str | None = Field(None, example="CloudScale AI LLC")
    deal_type: str | None = Field(None, example="Vendor Procurement")
    title: str = Field(..., example="Enterprise Cloud Hosting Services Agreement")
    description: str | None = None
    context_facts: str = Field(..., example="Vendor submitted proposal with Net 30 payment terms and 99.9% uptime SLA.")


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
    id: int
    deal_code: str | None
    company_name: str | None
    counterparty_name: str | None
    deal_type: str | None
    title: str
    description: str | None
    context_facts: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ClauseResponse(BaseModel):
    id: int
    organization: str
    counterparty: str | None
    agreement_type: str
    domain: str | None
    title: str | None
    section: str | None
    parent_section: str | None
    hierarchy_level: str
    authority_class: str
    effective_date: datetime | None
    expiration_date: datetime | None
    superseded: bool
    terminated: bool
    superseded_by: str | None
    content: str
    source_header: str | None
    sim_score: float | None = None
    fts_score: float | None = None
    rrf_score: float | None = None

    class Config:
        from_attributes = True


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
    brief_content: str
    claims_audit: list[dict[str, Any]] | None = None
    retrieved_clauses: list[dict[str, Any]] | None = None
    disclaimer: str | None = None


class IngestDocumentRequest(BaseModel):
    file_path: str
    deal_id: int | None = None
    doc_type: str = "contract"
    organization: str = "Acme Corp"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint confirming database and model availability."""
    db_ok = False
    try:
        db.execute(text("SELECT 1;"))
        db_ok = True
    except Exception as e:
        logger.error(f"Health check database failure: {e}")

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "kruschbiz-backend",
        "version": "0.3.0",
        "database_connected": db_ok,
        "is_sqlite": settings.is_sqlite,
        "embedding_model": settings.OLLAMA_EMBED_MODEL,
        "llm_model": settings.OLLAMA_LLM_MODEL
    }


# --- Deal Matters CRUD ---
@app.post("/api/deals", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
def create_deal(
    payload: DealCreate,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Create a new corporate deal or transaction matter with vector embedding."""
    logger.info(f"Creating corporate deal: '{payload.title}'...")
    vec = None
    try:
        vec = get_embedding(f"{payload.title} {payload.context_facts}")
    except Exception as e:
        logger.warning(f"Could not generate embedding for deal ({e}).")

    deal = DealMatter(
        deal_code=payload.deal_code,
        company_name=payload.company_name,
        counterparty_name=payload.counterparty_name,
        deal_type=payload.deal_type,
        title=payload.title,
        description=payload.description,
        context_facts=payload.context_facts,
        status="active",
        embedding=vec
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return deal


@app.get("/api/deals", response_model=list[DealResponse])
def list_deals(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Enumerate active corporate deals and matters."""
    return db.query(DealMatter).filter(
        DealMatter.is_deleted == False
    ).order_by(DealMatter.created_at.desc()).offset(offset).limit(limit).all()


@app.get("/api/deals/{deal_id}", response_model=DealResponse)
def get_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Retrieve details for a specific deal matter."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.is_deleted == False
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")
    return deal


@app.patch("/api/deals/{deal_id}", response_model=DealResponse)
def update_deal(
    deal_id: int,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Update deal matter attributes or facts."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.is_deleted == False
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")

    update_data = payload.model_dump(exclude_unset=True)
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
    api_key: str | None = Depends(verify_api_key)
):
    """Soft delete a deal matter from active listings."""
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.is_deleted == False
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal matter #{deal_id} not found.")
    deal.is_deleted = True
    db.commit()
    return {"status": "success", "message": f"Deal #{deal_id} soft deleted."}


@app.delete("/api/deals/{deal_id}/purge", status_code=status.HTTP_200_OK)
def hard_purge_deal(
    deal_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """
    Cryptographic hard purge: Permanently delete deal record, all associated evidence,
    and grounding reports, recording an immutable audit entry.
    """
    deal = db.query(DealMatter).filter(DealMatter.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")

    # Remove evidence
    ev_count = db.query(DealEvidence).filter(DealEvidence.deal_id == deal_id).delete()
    # Remove grounding reports
    rep_count = db.query(CommercialGroundingReport).filter(CommercialGroundingReport.deal_id == deal_id).delete()
    # Remove deal
    db.delete(deal)

    # Immutable audit log
    audit = AuditLog(
        action="purge_deal",
        deal_id=deal_id,
        duration_ms=0,
        grounding_verdict="PURGED"
    )
    db.add(audit)
    db.commit()
    return {
        "status": "success",
        "message": f"Deal #{deal_id} permanently purged ({ev_count} evidence records, {rep_count} grounding reports)."
    }


# --- Clauses & Contract Search ---
@app.get("/api/clauses", response_model=list[ClauseResponse])
def search_clauses(
    q: str | None = Query(None, description="Natural language search or clause keywords"),
    organization: str | None = Query(None),
    agreement_type: str | None = Query(None),
    domain: str | None = Query(None),
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Hybrid semantic (ANN) + lexical search across versioned corporate contracts and policies."""
    if q and q.strip():
        results = retrieve_clauses(
            db=db,
            query=q.strip(),
            limit=limit,
            offset=offset,
            organization=organization,
            agreement_type=agreement_type,
            domain=domain
        )
        return results

    query_obj = db.query(CommercialClauseVector).filter(
        CommercialClauseVector.superseded == False,
        CommercialClauseVector.terminated == False
    )
    if organization:
        query_obj = query_obj.filter(CommercialClauseVector.organization.ilike(f"%{organization}%"))
    if agreement_type:
        query_obj = query_obj.filter(CommercialClauseVector.agreement_type.ilike(f"%{agreement_type}%"))
    if domain:
        query_obj = query_obj.filter(CommercialClauseVector.domain.ilike(f"%{domain}%"))

    records = query_obj.offset(offset).limit(limit).all()
    return records


@app.get("/api/clauses/{clause_id}", response_model=ClauseResponse)
def get_clause(
    clause_id: int,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Retrieve full text and metadata for a specific clause."""
    cl = db.query(CommercialClauseVector).filter(CommercialClauseVector.id == clause_id).first()
    if not cl:
        raise HTTPException(status_code=404, detail=f"Clause #{clause_id} not found.")
    return cl


# --- Deal Room Evidence ---
@app.get("/api/deals/{deal_id}/evidence")
def get_deal_evidence(
    deal_id: int,
    q: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Retrieve isolated discovery exhibits and evidence for a specific deal matter."""
    deal = db.query(DealMatter).filter(DealMatter.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")

    query_obj = db.query(DealEvidence).filter(DealEvidence.deal_id == deal_id)
    if q:
        query_obj = query_obj.filter(DealEvidence.content.ilike(f"%{q}%"))

    records = query_obj.limit(limit).all()
    return [
        {
            "id": r.id,
            "deal_id": r.deal_id,
            "filename": r.filename,
            "doc_type": r.doc_type,
            "page_number": r.page_number,
            "section_locator": r.section_locator,
            "content": r.content,
            "created_at": r.created_at
        }
        for r in records
    ]


# --- Consultation & Executive Brief Generation ---
@app.get("/api/consult", response_model=ConsultResponse)
def consult_deal(
    deal_id: int | None = None,
    query: str | None = None,
    limit: int = 5,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """
    Run corporate intelligence consult:
    Synthesizes 4-part executive brief with commercial assertion-level grounding.
    """
    start_time = time.time()

    if deal_id is not None:
        deal = db.query(DealMatter).filter(
            DealMatter.id == deal_id,
            DealMatter.is_deleted == False
        ).first()
        if not deal:
            raise HTTPException(status_code=404, detail=f"Deal #{deal_id} not found.")
        deal_title = deal.title
        deal_code = deal.deal_code
        counterparty = deal.counterparty_name
        deal_type = deal.deal_type
        context_facts = deal.context_facts
        search_query = query or f"{deal_title} {context_facts}"

        # Fetch isolated evidence
        evidence_records = db.query(DealEvidence).filter(DealEvidence.deal_id == deal_id).all()
        evidence = [
            {"filename": e.filename, "page_number": e.page_number, "section_locator": e.section_locator, "content": e.content}
            for e in evidence_records
        ]
    else:
        if not query or not query.strip():
            raise HTTPException(status_code=400, detail="Must provide either 'deal_id' or 'query'.")
        deal_title = "Ad-Hoc Transaction Analysis"
        deal_code = "ADHOC"
        counterparty = None
        deal_type = "Commercial Inquiry"
        context_facts = query
        search_query = query
        evidence = []

    # 1. Retrieve commercial authorities
    clauses = retrieve_clauses(db=db, query=search_query, limit=limit)

    # 2. Generate executive brief with assertion-level verification
    brief_text, stats, claims_audit = generate_executive_brief(
        deal_title=deal_title,
        context_facts=context_facts,
        clauses=clauses,
        evidence=evidence,
        deal_code=deal_code,
        counterparty=counterparty,
        deal_type=deal_type,
        deal_id=deal_id,
        db=db
    )

    elapsed_ms = int((time.time() - start_time) * 1000)

    # Record audit log
    try:
        audit = AuditLog(
            action="consult",
            deal_id=deal_id,
            retrieved_clause_ids=",".join(str(c.get("id")) for c in clauses if c.get("id")),
            model_name=settings.OLLAMA_LLM_MODEL,
            prompt_hash=hashlib.sha256(search_query.encode()).hexdigest(),
            grounding_verdict="PASS" if stats.get("pass_rate", 0) >= 90 else "WARNING",
            duration_ms=elapsed_ms
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        logger.warning(f"Could not record audit log: {e}")

    return {
        "deal_id": deal_id,
        "deal_title": deal_title,
        "counterparty": counterparty,
        "analysis": brief_text,
        "grounding_stats": stats,
        "claims_audit": claims_audit,
        "retrieved_clauses": clauses
    }


# --- Document Ingestion (KruschNexus) ---
@app.post("/api/ingest/upload")
def upload_document(
    file: UploadFile = File(...),
    deal_id: int | None = Form(None),
    doc_type: str = Form("contract"),
    organization: str = Form("Acme Corp"),
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Multipart file upload ingested via KruschNexus sovereign parser & chunker."""
    try:
        report = ingest_uploaded_business_file(
            file=file,
            deal_id=deal_id,
            doc_type=doc_type,
            organization=organization,
            db=db
        )
        return report
    except ValueError as e:
        logger.warning(f"Invalid uploaded document request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to ingest uploaded document: {e}")
        raise HTTPException(status_code=500, detail=f"Document ingestion failed: {e}")


@app.post("/api/ingest/document")
def ingest_local_document(
    payload: IngestDocumentRequest,
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Ingest a server-local file path via KruschNexus."""
    try:
        report = ingest_business_document(
            file_path=payload.file_path,
            deal_id=payload.deal_id,
            doc_type=payload.doc_type,
            organization=payload.organization,
            db=db
        )
        return report
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Document ingestion error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@app.post("/api/ingest/mock")
@app.post("/api/ingest/seed")
def seed_fixtures(
    db: Session = Depends(get_db),
    api_key: str | None = Depends(verify_api_key)
):
    """Seed demo corporate contract and policy fixtures into the database."""
    report = ingest_mock_data(db)
    return report


# --- Export Endpoints ---
@app.post("/api/consult/export/docx")
def export_docx(
    payload: ExportDocxRequest,
    api_key: str | None = Depends(verify_api_key)
):
    """Generate and download a professional Word (.docx) executive memorandum."""
    docx_bytes = generate_brief_docx(
        brief_content=payload.brief_content,
        deal_title=payload.deal_title,
        deal_code=payload.deal_code,
        counterparty=payload.counterparty,
        deal_type=payload.deal_type,
        claims_audit=payload.claims_audit,
        retrieved_clauses=payload.retrieved_clauses,
        disclaimer=payload.disclaimer
    )
    filename = f"Executive_Brief_{payload.deal_code or 'DEAL'}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.post("/api/consult/export/md")
def export_md(
    payload: ExportDocxRequest,
    api_key: str | None = Depends(verify_api_key)
):
    """Generate and return structured Markdown with audit tables."""
    md_text = generate_brief_markdown(
        brief_content=payload.brief_content,
        deal_title=payload.deal_title,
        deal_code=payload.deal_code,
        counterparty=payload.counterparty,
        deal_type=payload.deal_type,
        claims_audit=payload.claims_audit,
        retrieved_clauses=payload.retrieved_clauses,
        disclaimer=payload.disclaimer
    )
    return {"markdown": md_text}
