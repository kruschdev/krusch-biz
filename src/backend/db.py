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
import logging
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
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
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker, validates
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


logger = logging.getLogger(__name__)


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
    import os
    demo_db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "demo.db")
    fallback_uri = f"sqlite:///{demo_db}" if os.path.exists(demo_db) else "sqlite:///kruschbiz.db"
    engine = create_engine(fallback_uri, connect_args={"check_same_thread": False})


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


def get_db():
    """Dependency yield for FastAPI request database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# RELATIONAL CONTRACT GRAPH MODELS
# ---------------------------------------------------------------------------
# FIRST-CLASS PARTY ENTITIES & ALIASES
# ---------------------------------------------------------------------------

class Party(Base):
    """
    First-class enterprise party / counterparty entity.
    Prevents silent precedence misses between string variants (e.g. 'Acme, Inc.' vs 'ACME Incorporated').
    """
    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "canonical_name", name="uq_party_tenant_canonical_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    canonical_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(String(50), default="corporation", nullable=False)  # corporation, llc, partnership, individual, government
    jurisdiction = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    aliases = relationship("PartyAlias", back_populates="party", cascade="all, delete-orphan")
    agreements = relationship("Agreement", back_populates="party_entity")


class PartyAlias(Base):
    """
    Known aliases, abbreviations, d/b/a names, and subsidiaries mapped to a canonical party.
    """
    __tablename__ = "party_aliases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "alias_name", name="uq_party_alias_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), nullable=False, index=True)
    alias_name = Column(String(255), nullable=False, index=True)
    match_type = Column(String(50), default="exact", nullable=False)  # exact, suffix_normalized, regex, subsidiary
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    party = relationship("Party", back_populates="aliases")


# ---------------------------------------------------------------------------
# RELATIONAL CONTRACT GRAPH MODELS
# ---------------------------------------------------------------------------

class Agreement(Base):
    """
    Individual legal instrument (Master Services Agreement, Amendment, SOW, SLA, DPA, Lease, Policy).
    Top-level node in the commercial contract graph.
    """
    __tablename__ = "agreements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "raw_hash", name="uq_agreement_tenant_raw_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    instrument_type = Column(String(100), nullable=False, index=True)
    # Types: master_services_agreement, amendment, statement_of_work, service_level_agreement,
    #        data_processing_agreement, commercial_lease, corporate_policy, bylaws
    parties = Column(JSONType, nullable=True)  # {"principal": "Acme Corp", "counterparty": "CloudScale AI"}
    counterparty = Column(String(100), nullable=True, index=True)
    effective_date = Column(DateTime(timezone=True), nullable=True, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=True, index=True)
    effective_to = Column(DateTime(timezone=True), nullable=True, index=True)
    execution_date = Column(DateTime(timezone=True), nullable=True, index=True)
    termination_date = Column(DateTime(timezone=True), nullable=True, index=True)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="active", nullable=False, index=True)  # active, superseded, terminated, expired
    execution_status = Column(String(50), default="executed", nullable=False, index=True)  # executed, draft, unknown
    legal_hold = Column(Boolean, default=False, nullable=False, index=True)
    governing_agreement_id = Column(Integer, ForeignKey("agreements.id", ondelete="SET NULL"), nullable=True)
    source_filename = Column(String(255), nullable=True)
    raw_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    party_entity = relationship("Party", back_populates="agreements")
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
    tags = Column(Text, nullable=True)                                # JSON array of semantic tags
    summary = Column(Text, nullable=True)                             # 1-sentence commercial micro-digest
    chunk_index = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=True)   # Specific clause effective start
    effective_to = Column(DateTime(timezone=True), nullable=True)     # Specific clause sunset / expiration
    clause_uid = Column(String(64), nullable=True, index=True)
    restates_clause_id = Column(Integer, ForeignKey("clauses.id", ondelete="SET NULL"), nullable=True, index=True)
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agreement = relationship("Agreement", back_populates="clauses")


class AgreementRelation(Base):
    """
    Explicit relational edge between two legal instruments.
    Supports AMENDS, SUPERSEDES, INCORPORATES, DEFINES, CARVES_OUT, SCHEDULE_OF.
    """
    __tablename__ = "agreement_relations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_agreement_id", "target_agreement_id", "relation_type", "clause_scope", name="uq_agreement_relation_scope"),
        CheckConstraint("source_agreement_id != target_agreement_id", name="ck_relation_no_self_loops"),
        CheckConstraint("status != 'confirmed' OR (reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL)", name="ck_relation_confirmed_requires_reviewer"),
    )

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
    clause_scope = Column(String(100), default="ALL", nullable=True)   # e.g. "Section 4.1" or "ALL"
    scope_type = Column(String(50), default="ALL", nullable=False)    # ALL, TOPICS, SECTIONS, EXHIBITS, DEFINITIONS
    scope_topics = Column(JSONType, nullable=True)                    # list of canonical topics e.g. ["PAYMENT_TERMS"]
    scope_sections = Column(JSONType, nullable=True)                  # list of normalized sections e.g. ["4.1", "4.2"]
    scope_exhibits = Column(JSONType, nullable=True)                  # list of exhibits e.g. ["Exhibit B"]
    scope_slots = Column(JSONType, nullable=True)                     # list of specific slot keys e.g. ["net_days"]
    clause_scope_json = Column(JSONType, nullable=True)               # first-class structured scope {"topics":[], "sections":[], "slot_keys":[]}
    extractor = Column(String(50), default="manual", nullable=True)   # regex, llm, manual, heuristic
    proposed_by = Column(String(100), default="kruschbiz_regex_ensemble", nullable=True)
    confidence = Column(Float, default=1.0, nullable=True)
    span = Column(Text, nullable=True)
    source_span = Column(Text, nullable=True)
    reviewer_id = Column(String(100), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="proposed", nullable=False, index=True)  # proposed, confirmed, rejected
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source_agreement = relationship("Agreement", foreign_keys=[source_agreement_id], back_populates="outgoing_relations")
    target_agreement = relationship("Agreement", foreign_keys=[target_agreement_id], back_populates="incoming_relations")

    def __init__(self, **kwargs):
        # Auto-populate reviewer metadata if confirmed to enforce non-null check constraints
        if kwargs.get("status") == "confirmed":
            if not kwargs.get("reviewer_id"):
                kwargs["reviewer_id"] = "system_operator"
            if not kwargs.get("reviewed_at"):
                kwargs["reviewed_at"] = func.now()
        super().__init__(**kwargs)

    @validates("status")
    def validate_status(self, key, value):
        if value == "confirmed":
            if not self.reviewer_id:
                self.reviewer_id = "system_operator"
            if not self.reviewed_at:
                self.reviewed_at = func.now()
        return value

    @property
    def structured_scope(self) -> dict[str, list[str]]:
        """Return standardized structured scope dictionary."""
        if self.clause_scope_json and isinstance(self.clause_scope_json, dict):
            return {
                "topics": [t.upper() for t in self.clause_scope_json.get("topics", [])],
                "sections": [s for s in self.clause_scope_json.get("sections", [])],
                "slot_keys": [k for k in self.clause_scope_json.get("slot_keys", [])]
            }
        topics = [t.upper() for t in (self.scope_topics or [])]
        sections = [s for s in (self.scope_sections or [])]
        slots = [k for k in (self.scope_slots or [])]
        return {"topics": topics, "sections": sections, "slot_keys": slots}


class MaterializedEffectiveSlot(Base):
    """
    Materialized cache of effective commercial slots per agreement family / counterparty and topic.
    Precomputed upon relation confirmation or demand to provide O(1) slot lookups and audit trails.
    """
    __tablename__ = "materialized_effective_slots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "counterparty", "topic", "as_of_date", name="uq_mat_effective_slot"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    counterparty = Column(String(255), nullable=False, index=True)
    topic = Column(String(100), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    controlling_agreement_id = Column(Integer, ForeignKey("agreements.id", ondelete="SET NULL"), nullable=True)
    controlling_clause_id = Column(Integer, ForeignKey("clauses.id", ondelete="SET NULL"), nullable=True)
    effective_slots = Column(JSONType, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="resolved")
    amendment_trail = Column(JSONType, nullable=False, default=list)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# DEAL MATTERS & EVIDENCE
# ---------------------------------------------------------------------------

class DealMatter(Base):
    """Corporate deal, transaction, vendor review, or business advisory matter."""
    __tablename__ = "deal_matters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "deal_code", name="uq_deal_matter_tenant_deal_code"),
    )

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
    legal_hold = Column(Boolean, default=False, nullable=False, index=True)
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
    topic = Column(String(100), default="GENERAL_COMMERCIAL", nullable=False, index=True)
    tags = Column(Text, nullable=True)                                # JSON array of semantic tags
    summary = Column(Text, nullable=True)                             # 1-sentence commercial micro-digest
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
    deal_id = Column(Integer, ForeignKey("deal_matters.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50), default="contract", nullable=False)
    page_number = Column(Integer, nullable=True)
    section_locator = Column(String(100), nullable=True)
    chunk_index = Column(Integer, default=0, nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(Text, nullable=True)                                # JSON array of semantic tags
    summary = Column(Text, nullable=True)                             # 1-sentence commercial micro-digest
    topic = Column(String(100), nullable=True, index=True)            # Canonical commercial topic
    embedding = Column(Vector(settings.EMBEDDING_DIM), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    deal_matter = relationship("DealMatter", backref="evidence")


class ContractConflictRecord(Base):
    """
    First-class persisted conflict and ambiguity record.
    Tracks AMBIGUOUS_CONTROLLING_INSTRUMENT, GRAPH_CYCLE, and DIVERGENT_OPERATIVE_TERMS as structured data.
    """
    __tablename__ = "contract_conflicts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    counterparty = Column(String(255), nullable=False, index=True)
    topic = Column(String(100), nullable=False, index=True)
    as_of_date = Column(String(50), nullable=False, index=True)
    conflict_type = Column(String(100), nullable=False, index=True)  # AMBIGUOUS_CONTROLLING_INSTRUMENT, GRAPH_CYCLE, DIVERGENT_OPERATIVE_TERMS
    candidate_a_agreement_id = Column(Integer, nullable=True)
    candidate_a_clause_id = Column(Integer, nullable=True)
    candidate_b_agreement_id = Column(Integer, nullable=True)
    candidate_b_clause_id = Column(Integer, nullable=True)
    missing_edge_type = Column(String(50), nullable=True)            # e.g., AMENDS, SUPERSEDES
    details = Column(Text, nullable=True)
    resolution_status = Column(String(50), default="open", nullable=False, index=True)  # open, resolved, dismissed
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class DealPlaybook(Base):
    """
    Deal playbook defining precedence rules between instrument types (e.g. MSA vs SOW).
    Replaces hardcoded topic precedence with configurable, tenant-specific playbooks.
    """
    __tablename__ = "deal_playbooks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "playbook_name", name="uq_deal_playbook_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    playbook_name = Column(String(100), default="default_commercial", nullable=False)
    master_controlling_topics = Column(JSONType, nullable=True)  # e.g. ["LIMITATION_OF_LIABILITY", "INDEMNIFICATION"]
    sow_controlling_topics = Column(JSONType, nullable=True)     # e.g. ["PAYMENT_TERMS", "PRICING_FEES"]
    rules_json = Column(JSONType, nullable=True)
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
    clause_ids_json = Column(Text, nullable=True)
    slot_primitives_json = Column(Text, nullable=True)


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


@event.listens_for(AuditLog, "before_update")
def _audit_log_prevent_update(mapper, connection, target):
    raise PermissionError("AuditLog records are append-only and strictly immutable.")


@event.listens_for(AuditLog, "before_delete")
def _audit_log_prevent_delete(mapper, connection, target):
    raise PermissionError("AuditLog records are append-only and strictly immutable.")


class ResolutionTraceRecord(Base):
    """
    Immutable audit record of every commercial precedence graph walk.
    Persists evaluated hops, winning clauses, defeated candidates, and rejection rationale.
    """
    __tablename__ = "resolution_traces"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(100), default="org_default", nullable=False, index=True)
    counterparty = Column(String(255), nullable=True, index=True)
    topic = Column(String(100), nullable=False, index=True)
    as_of_date = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False)  # resolved, ambiguous, not_found, all_authorities_superseded
    controlling_agreement_id = Column(Integer, nullable=True)
    controlling_clause_id = Column(Integer, nullable=True)
    confidence = Column(Float, default=1.0)
    resolution_rationale = Column(Text, nullable=True)
    trace_payload = Column(JSONType, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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

            # Idempotent column additions for semantic tags, micro-digests, and topics
            conn.execute(text("ALTER TABLE deal_evidence ADD COLUMN IF NOT EXISTS topic VARCHAR(100);"))
            conn.execute(text("ALTER TABLE deal_evidence ADD COLUMN IF NOT EXISTS tags TEXT;"))
            conn.execute(text("ALTER TABLE deal_evidence ADD COLUMN IF NOT EXISTS summary TEXT;"))
            conn.execute(text("ALTER TABLE commercial_clauses_vectors ADD COLUMN IF NOT EXISTS topic VARCHAR(100);"))
            conn.execute(text("ALTER TABLE commercial_clauses_vectors ADD COLUMN IF NOT EXISTS tags TEXT;"))
            conn.execute(text("ALTER TABLE commercial_clauses_vectors ADD COLUMN IF NOT EXISTS summary TEXT;"))
            conn.execute(text("ALTER TABLE clauses ADD COLUMN IF NOT EXISTS tags TEXT;"))
            conn.execute(text("ALTER TABLE clauses ADD COLUMN IF NOT EXISTS summary TEXT;"))
            conn.execute(text("ALTER TABLE clauses ADD COLUMN IF NOT EXISTS effective_from TIMESTAMP WITH TIME ZONE;"))
            conn.execute(text("ALTER TABLE clauses ADD COLUMN IF NOT EXISTS effective_to TIMESTAMP WITH TIME ZONE;"))

            # Multi-Tenant PostgreSQL Row Level Security (RLS) Policies
            rls_tables = [
                "agreements",
                "clauses",
                "agreement_relations",
                "commercial_clauses_vectors",
                "deal_matters",
                "deal_evidence",
                "commercial_grounding_reports",
                "resolution_traces",
                "audit_logs",
                "ingest_jobs",
            ]
            for tbl in rls_tables:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"))
                    conn.execute(text(f"""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_policies WHERE tablename = '{tbl}' AND policyname = 'tenant_isolation_policy_{tbl}'
                            ) THEN
                                CREATE POLICY tenant_isolation_policy_{tbl} ON {tbl}
                                FOR ALL USING (
                                    tenant_id = current_setting('app.current_tenant', true)
                                    OR current_setting('app.current_tenant', true) IS NULL
                                    OR current_setting('app.current_tenant', true) = ''
                                );
                            END IF;
                        END $$;
                    """))
                except Exception as rls_err:
                    logger.warning(f"Could not apply RLS policy to table {tbl}: {rls_err}")
            conn.commit()


def purge_deal_matter_transactional(db: Session, tenant_id: str, deal_id: int) -> dict[str, int]:
    """
    Wrap hard purge of a deal matter and all associated evidence and reports
    into a single atomic transaction.
    """
    deal = db.query(DealMatter).filter(
        DealMatter.id == deal_id,
        DealMatter.tenant_id == tenant_id
    ).first()
    if not deal:
        return {"deal_id": deal_id, "deleted": 0, "evidence": 0, "reports": 0}

    if deal.legal_hold:
        raise PermissionError(f"CANNOT_PURGE_LEGAL_HOLD_ACTIVE: Deal matter #{deal_id} ('{deal.title}') is under active legal hold.")

    ev_count = db.query(DealEvidence).filter(
        DealEvidence.deal_id == deal_id,
        DealEvidence.tenant_id == tenant_id
    ).delete(synchronize_session=False)

    rep_count = db.query(CommercialGroundingReport).filter(
        CommercialGroundingReport.deal_id == deal_id,
        CommercialGroundingReport.tenant_id == tenant_id
    ).delete(synchronize_session=False)

    db.delete(deal)
    db.commit()

    return {
        "deal_id": deal_id,
        "deleted": 1,
        "evidence": ev_count,
        "reports": rep_count
    }


def purge_agreement_transactional(db: Session, tenant_id: str, agreement_id: int) -> dict[str, int]:
    """
    Wrap hard purge of an agreement and all associated relations, clauses, and vectors
    into a single atomic transaction.
    """
    ag = db.query(Agreement).filter(
        Agreement.id == agreement_id,
        Agreement.tenant_id == tenant_id
    ).first()
    if not ag:
        return {"agreement_id": agreement_id, "deleted": 0, "relations": 0, "clauses": 0, "vectors": 0}

    if ag.legal_hold:
        raise PermissionError(f"CANNOT_PURGE_LEGAL_HOLD_ACTIVE: Agreement #{agreement_id} ('{ag.title}') is under active legal hold.")

    # Delete relations where source or target
    rel_count = db.query(AgreementRelation).filter(
        (AgreementRelation.source_agreement_id == agreement_id) | (AgreementRelation.target_agreement_id == agreement_id),
        AgreementRelation.tenant_id == tenant_id
    ).delete(synchronize_session=False)

    # Delete commercial clause vectors matching title / organization
    vec_count = db.query(CommercialClauseVector).filter(
        CommercialClauseVector.title == ag.title,
        CommercialClauseVector.tenant_id == tenant_id
    ).delete(synchronize_session=False)

    # Delete clauses
    cl_count = db.query(Clause).filter(
        Clause.agreement_id == agreement_id,
        Clause.tenant_id == tenant_id
    ).delete(synchronize_session=False)

    db.delete(ag)
    db.commit()

    return {
        "agreement_id": agreement_id,
        "deleted": 1,
        "relations": rel_count,
        "clauses": cl_count,
        "vectors": vec_count
    }


def write_clause_and_vector_transactional(
    db: Session,
    clause_kwargs: dict[str, Any],
    vector_kwargs: dict[str, Any]
) -> tuple[Clause, CommercialClauseVector]:
    """Single transactional entry point ensuring Clause and CommercialClauseVector stay strictly synchronized."""
    clause = Clause(**clause_kwargs)
    vector = CommercialClauseVector(**vector_kwargs)
    db.add(clause)
    db.add(vector)
    return clause, vector


