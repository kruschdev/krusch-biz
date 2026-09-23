"""
src/backend/db.py
=================
Sovereign corporate database schema for KruschBiz.
Features:
  - Relational contract graph: Agreements -> Clauses -> Agreement Relations (AMENDS, SUPERSEDES)
  - Multi-tenant boundary isolation (tenant_id)
  - Structured commercial slots (net_days, uptime_pct, late_interest_pct, cap_period_months)
  - Dual dialect support: PostgreSQL (pgvector HNSW + full-text GIN) and SQLite (in-memory & file)
  - Strict Foreign Key cascade constraints
"""

import json
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.types import UserDefinedType

from .config import settings

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    class Vector(UserDefinedType):
        cache_ok = True

        def __init__(self, dim=1024):
            self.dim = dim

        def get_col_spec(self, **kw):
            return "TEXT"

        def bind_processor(self, dialect):
            def process(value):
                return json.dumps(value) if isinstance(value, list) else value
            return process

        def result_processor(self, dialect, coltype):
            def process(value):
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except Exception:
                        return value
                return value
            return process


class JSONType(UserDefinedType):
    """Cross-dialect JSON serialization column."""
    cache_ok = True

    def get_col_spec(self, **kw):
        return "TEXT"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return json.dumps(value) if not isinstance(value, str) else value
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return value
            return value
        return process


# Configure engine based on dialect
engine_kwargs = {}
if settings.is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

try:
    engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
except (ImportError, Exception) as exc:
    import logging
    logging.getLogger("kruschbiz.db").warning(
        f"Database engine initialization failed ({exc}). Falling back to local SQLite engine."
    )
    engine = create_engine("sqlite:///kruschbiz.db", connect_args={"check_same_thread": False})


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints on SQLite connections."""
    if "sqlite" in str(type(dbapi_connection)).lower() or hasattr(dbapi_connection, "cursor"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# RELATIONAL CONTRACT GRAPH MODELS
# ---------------------------------------------------------------------------

class Agreement(Base):
    """
    Individual legal instrument (Master Services Agreement, Amendment, SOW, SLA, DPA, Lease, Policy).
    Top-level node in the commercial contract graph.
    """
    __tablename__ = "agreements"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    instrument_type = Column(String(100), nullable=False, index=True)
    # Types: master_services_agreement, amendment, statement_of_work, service_level_agreement,
    #        data_processing_agreement, commercial_lease, corporate_policy, bylaws
    parties = Column(JSONType, nullable=True)  # {"principal": "Acme Corp", "counterparty": "CloudScale AI"}
    counterparty = Column(String(100), nullable=True, index=True)
    effective_date = Column(DateTime(timezone=True), nullable=True, index=True)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="active", nullable=False, index=True)  # active, superseded, terminated, expired
    governing_agreement_id = Column(Integer, ForeignKey("agreements.id", ondelete="SET NULL"), nullable=True)
    source_filename = Column(String(255), nullable=True)
    raw_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    clauses = relationship("Clause", back_populates="agreement", cascade="all, delete-orphan")
    outgoing_relations = relationship(
        "AgreementRelation",
        foreign_keys="AgreementRelation.source_agreement_id",
        back_populates="source_agreement",
        cascade="all, delete-orphan",
    )
    incoming_relations = relationship(
        "AgreementRelation",
        foreign_keys="AgreementRelation.target_agreement_id",
        back_populates="target_agreement",
        cascade="all, delete-orphan",
    )


class Clause(Base):
    """
    Specific clause, section, or provision within an agreement.
    Contains extracted structured slots and vector embedding.
    """
    __tablename__ = "clauses"
    __table_args__ = (
        CheckConstraint(
            "authority_class IN ('governing_agreement', 'amendment', 'amendment_addendum', 'executed_amendment', 'statement_of_work', 'corporate_policy', 'regulatory_framework', 'commercial_code', 'statutory_code', 'secondary_guideline')",
            name="ck_clause_authority_class"
        ),
        CheckConstraint(
            "hierarchy_level IN ('agreement', 'article', 'clause', 'subclause', 'sla_metric', 'carve_out', 'penalty')",
            name="ck_clause_hierarchy_level"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    agreement_id = Column(Integer, ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    section = Column(String(100), nullable=True, index=True)          # e.g., "Section 4.1"
    title = Column(String(255), nullable=True)                        # e.g., "Invoicing and Payment Terms"
    topic = Column(String(100), default="GENERAL_COMMERCIAL", nullable=False, index=True)  # from closed taxonomy
    hierarchy_level = Column(String(50), default="clause", nullable=False, index=True)
    authority_class = Column(String(50), default="governing_agreement", nullable=False, index=True)
    content = Column(Text, nullable=False)
    structured_slots = Column(JSONType, nullable=True)                # e.g. {"net_days": 30, "late_interest_pct": 1.5}
    chunk_index = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agreement = relationship("Agreement", back_populates="clauses")


class AgreementRelation(Base):
    """
    Explicit relational edge between two legal instruments.
    Supports AMENDS, SUPERSEDES, INCORPORATES, DEFINES, CARVES_OUT, SCHEDULE_OF.
    """
    __tablename__ = "agreement_relations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    source_agreement_id = Column(Integer, ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    target_agreement_id = Column(Integer, ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, index=True)
    # AMENDS: source amends target
    # SUPERSEDES: source supersedes target
    # INCORPORATES: source incorporates target by reference
    # SCHEDULE_OF: source is a statement of work or schedule under target
    # CARVES_OUT: source carves out terms from target
    effective_date = Column(DateTime(timezone=True), nullable=True)
    clause_scope = Column(String(100), nullable=True)                 # e.g. "Section 4.1" or "ALL"
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_agreement = relationship("Agreement", foreign_keys=[source_agreement_id], back_populates="outgoing_relations")
    target_agreement = relationship("Agreement", foreign_keys=[target_agreement_id], back_populates="incoming_relations")


# ---------------------------------------------------------------------------
# DEAL MATTERS & EVIDENCE
# ---------------------------------------------------------------------------

class DealMatter(Base):
    """Corporate deal, transaction, vendor review, or business advisory matter."""
    __tablename__ = "deal_matters"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    deal_code = Column(String(50), nullable=True, index=True)          # e.g., "DEAL-2026-001"
    company_name = Column(String(255), nullable=True, index=True)      # e.g., "Acme Corp"
    counterparty_name = Column(String(255), nullable=True, index=True) # e.g., "CloudScale AI LLC"
    deal_type = Column(String(100), nullable=True, index=True)         # e.g., "Vendor Procurement", "SaaS Licensing"
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    context_facts = Column(Text, nullable=False)                       # Background narrative and transaction context
    status = Column(String(50), default="active", nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)


class CommercialClauseVector(Base):
    """
    Flattened / denormalized commercial clause view for fast hybrid dense + lexical search.
    Synchronized with Agreement and Clause models.
    """
    __tablename__ = "commercial_clauses_vectors"
    __table_args__ = (
        UniqueConstraint("organization", "title", "section", "chunk_index", name="uq_clause_org_title_sec_chunk"),
        CheckConstraint(
            "authority_class IN ('governing_agreement', 'amendment', 'amendment_addendum', 'executed_amendment', 'statement_of_work', 'corporate_policy', 'regulatory_framework', 'commercial_code', 'statutory_code', 'secondary_guideline')",
            name="ck_vector_authority_class"
        ),
        CheckConstraint(
            "hierarchy_level IN ('agreement', 'article', 'clause', 'subclause', 'sla_metric', 'carve_out', 'penalty')",
            name="ck_vector_hierarchy_level"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    organization = Column(String(100), nullable=False, index=True)
    counterparty = Column(String(100), nullable=True, index=True)
    agreement_type = Column(String(100), nullable=False, index=True)
    domain = Column(String(100), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    section = Column(String(100), nullable=True, index=True)
    parent_section = Column(String(100), nullable=True, index=True)
    hierarchy_level = Column(String(50), default="clause", nullable=False, index=True)
    definitions_ref = Column(String(100), nullable=True)
    exceptions_ref = Column(String(100), nullable=True)
    authority_class = Column(String(50), default="governing_agreement", nullable=False, index=True)
    effective_date = Column(DateTime(timezone=True), nullable=True)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    amended_date = Column(DateTime(timezone=True), nullable=True)
    superseded = Column(Boolean, default=False, nullable=False, index=True)
    terminated = Column(Boolean, default=False, nullable=False, index=True)
    superseded_by = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    source_header = Column(Text, nullable=True)
    source_hash = Column(String(64), nullable=True, index=True)
    chunk_index = Column(Integer, default=0, nullable=False)
    is_substantive = Column(Boolean, default=True, nullable=False)
    structured_slots = Column(JSONType, nullable=True)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)


class DealEvidence(Base):
    """
    Deal room exhibits, vendor proposals, redlines, financial attachments, and emails.
    Strictly isolated per deal matter and tenant.
    """
    __tablename__ = "deal_evidence"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    deal_id = Column(Integer, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50), default="contract", nullable=False)
    page_number = Column(Integer, nullable=True)
    section_locator = Column(String(100), nullable=True)
    chunk_index = Column(Integer, default=0, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommercialGroundingReport(Base):
    """
    Immutable assertion-level grounding audit report tracking verified propositions,
    supporting contract excerpts, and commercial failure modes.
    """
    __tablename__ = "commercial_grounding_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    deal_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    total_claims = Column(Integer, default=0, nullable=False)
    supported_claims = Column(Integer, default=0, nullable=False)
    unsupported_claims = Column(Integer, default=0, nullable=False)
    invented_clauses = Column(Integer, default=0, nullable=False)
    divergent_terms = Column(Integer, default=0, nullable=False)
    superseded_terms = Column(Integer, default=0, nullable=False)
    pass_rate = Column(Float, default=100.0, nullable=False)
    claims_json = Column(Text, nullable=False)
    advisory_markdown = Column(Text, nullable=True)


class AuditLog(Base):
    """
    Per-action regulatory and corporate governance audit trail.
    Tracks deal consultations, clause searches, ingestion runs, and hard deletes.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_key_hash = Column(String(64), nullable=True, index=True)
    client_ip = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False, index=True)  # consult, search, ingest, delete_deal, hard_delete_deal, export
    deal_id = Column(Integer, nullable=True, index=True)
    retrieved_clause_ids = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=True)
    prompt_hash = Column(String(64), nullable=True)
    grounding_verdict = Column(String(50), nullable=True)    # PASS, WARNING, FAIL
    duration_ms = Column(Integer, nullable=True)


class IngestJob(Base):
    """
    Persistent, crash-resilient queue job for corporate corpora ingestion.
    Supports transactional resumption, byte deduplication, and stage telemetry.
    """
    __tablename__ = "ingest_jobs"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    raw_file_hash = Column(String(64), nullable=True, index=True)
    status = Column(String(20), default="pending", nullable=False, index=True)  # pending, running, completed, failed, cancelled
    stage = Column(String(50), default="queued", nullable=False)
    total_rows = Column(Integer, default=0, nullable=False)
    processed_rows = Column(Integer, default=0, nullable=False)
    inserted_records = Column(Integer, default=0, nullable=False)
    last_committed_offset = Column(Integer, default=0, nullable=False)
    worker_id = Column(String(100), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    ocr_pages = Column(Integer, default=0, nullable=False)
    total_pages = Column(Integer, default=0, nullable=False)
    chunks_total = Column(Integer, default=0, nullable=False)
    chunks_embedded = Column(Integer, default=0, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def init_db(target_engine=None):
    """Initialize database tables, pgvector extension, HNSW vector indexes, and GIN full-text index."""
    eng = target_engine or engine
    dialect_name = eng.dialect.name

    if dialect_name == "postgresql":
        with eng.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

    Base.metadata.create_all(bind=eng)

    if dialect_name == "postgresql":
        with eng.connect() as conn:
            # HNSW cosine indexes
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS clauses_embedding_hnsw_idx
                ON clauses USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS commercial_clauses_embedding_hnsw_idx
                ON commercial_clauses_vectors USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS deal_matters_embedding_hnsw_idx
                ON deal_matters USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS deal_evidence_embedding_hnsw_idx
                ON deal_evidence USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """))
            # Functional GIN index for hybrid full-text search
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS commercial_clauses_search_tsv_idx
                ON commercial_clauses_vectors USING gin(
                    to_tsvector('english', coalesce(content, '') || ' ' || coalesce(title, '') || ' ' || coalesce(section, ''))
                );
            """))
            conn.commit()
