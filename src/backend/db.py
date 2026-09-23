import json
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy.types import UserDefinedType

    class Vector(UserDefinedType):
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

from .config import settings

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

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DealMatter(Base):
    """Corporate deal, transaction, vendor review, or business advisory matter."""
    __tablename__ = "deal_matters"

    id = Column(Integer, primary_key=True, index=True)
    deal_code = Column(String(50), nullable=True, index=True)          # e.g., "DEAL-2026-001"
    company_name = Column(String(255), nullable=True, index=True)      # e.g., "Acme Corp"
    counterparty_name = Column(String(255), nullable=True, index=True) # e.g., "CloudScale AI LLC"
    deal_type = Column(String(100), nullable=True, index=True)         # e.g., "Vendor Procurement", "SaaS Licensing", "M&A Due Diligence"
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    context_facts = Column(Text, nullable=False)                       # Background narrative and transaction context
    status = Column(String(50), default="active", nullable=False, index=True) # active, under_review, closed, archived
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)


class CommercialClauseVector(Base):
    """
    Corporate contract, MSA, SLA, SOW, corporate policy, or regulatory standard
    in a hierarchical, versioned commercial graph with dense vector embeddings.
    """
    __tablename__ = "commercial_clauses_vectors"
    __table_args__ = (
        UniqueConstraint("organization", "agreement_type", "section", "chunk_index", name="uq_clause_section_chunk"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization = Column(String(100), nullable=False, index=True)      # e.g., "Acme Corp", "Commercial Standard"
    counterparty = Column(String(100), nullable=True, index=True)       # e.g., "CloudScale AI"
    agreement_type = Column(String(100), nullable=False, index=True)    # e.g., "Master Services Agreement", "Service Level Agreement"
    domain = Column(String(100), nullable=True, index=True)             # e.g., "Procurement & Invoicing", "Risk & Indemnification"
    title = Column(String(255), nullable=True)                         # e.g., "Acme MSA: Limitation of Liability"
    section = Column(String(100), nullable=True, index=True)           # e.g., "Section 10.1"
    parent_section = Column(String(100), nullable=True, index=True)    # e.g., "Article X"
    hierarchy_level = Column(String(50), default="clause", nullable=False, index=True) # agreement, article, clause, subclause, definition, sla_metric, carve_out, penalty
    definitions_ref = Column(String(100), nullable=True)               # e.g., "Section 1.1"
    exceptions_ref = Column(String(100), nullable=True)                # e.g., "Section 10.2"

    authority_class = Column(String(50), default="governing_agreement", nullable=False, index=True)
    # Options: governing_agreement, amendment_addendum, statement_of_work, corporate_policy, regulatory_framework, commercial_code, secondary_guideline

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
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)


class DealEvidence(Base):
    """
    Deal room exhibits, vendor proposals, redlines, financial attachments, and emails.
    Strictly isolated per deal matter to prevent cross-account information leakage.
    """
    __tablename__ = "deal_evidence"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(Integer, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50), default="contract", nullable=False)  # contract, redline, invoice, email, financial_statement, due_diligence_exhibit
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
    deal_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    total_claims = Column(Integer, default=0, nullable=False)
    supported_claims = Column(Integer, default=0, nullable=False)
    unsupported_claims = Column(Integer, default=0, nullable=False)
    invented_clauses = Column(Integer, default=0, nullable=False)
    superseded_terms = Column(Integer, default=0, nullable=False)
    pass_rate = Column(Float, default=100.0, nullable=False)
    claims_json = Column(Text, nullable=False)
    advisory_markdown = Column(Text, nullable=True)


class AuditLog(Base):
    """
    Per-action regulatory and corporate governance audit trail.
    Tracks deal consultations, clause searches, ingestion runs, and hard purges.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor_key_hash = Column(String(64), nullable=True, index=True)
    client_ip = Column(String(50), nullable=True)
    action = Column(String(50), nullable=False, index=True)            # consult, search, ingest, delete_deal, purge_deal, export
    deal_id = Column(Integer, nullable=True, index=True)
    retrieved_clause_ids = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=True)
    model_version = Column(String(50), nullable=True)
    prompt_hash = Column(String(64), nullable=True)
    grounding_verdict = Column(String(50), nullable=True)              # PASS, WARNING, FAIL
    duration_ms = Column(Integer, nullable=True)


class IngestJob(Base):
    """
    Persistent, crash-resilient queue job for corporate corpora ingestion.
    Supports transactional resumption, byte deduplication, and stage telemetry.
    """
    __tablename__ = "ingest_jobs"

    id = Column(String(36), primary_key=True)
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
            # HNSW cosine indexes for sub-millisecond retrieval on large contract corpora
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
            # Functional GIN index for hybrid full-text lexical search
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS commercial_clauses_search_tsv_idx
                ON commercial_clauses_vectors USING gin (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(section, '') || ' ' || coalesce(content, '')));
            """))
            conn.commit()
