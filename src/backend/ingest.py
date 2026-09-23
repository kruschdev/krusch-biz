"""
src/backend/ingest.py
=====================
Corporate contract, deal exhibit, and policy document ingestion engine.
Features:
  - Universal parsing via KruschNexus or standalone fallback adapter
  - MIME magic byte verification
  - Maximum chunk count per document (DOS protection)
  - Open structured slot extraction into JSON schemas
  - Dual population of relational graph (Agreements -> Clauses -> Agreement Relations)
    and denormalized CommercialClauseVector for fast hybrid search
  - Transactional IngestJob state machine (queued -> parsing -> chunking -> extracting_slots -> embedding -> indexed | failed)
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .config import settings
from .db import (
    Agreement,
    AgreementRelation,
    Clause,
    CommercialClauseVector,
    DealEvidence,
    IngestJob,
    SessionLocal,
)
from .nexus_adapter import chunk_document, parse_document
from .rag import get_embeddings_batch
from .taxonomy import extract_structured_slots

logger = logging.getLogger("kruschbiz.ingest")

MAX_INGEST_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_INGEST_CHUNKS_PER_DOC = 1000


def validate_file_magic_bytes(file_path: str, ext: str) -> bool:
    """Validate that file headers match declared extension to prevent MIME-spoofing."""
    if not os.path.exists(file_path):
        return False
    with open(file_path, "rb") as f:
        header = f.read(16)
    ext = ext.lower()
    if ext == ".pdf":
        return header.startswith(b"%PDF-")
    elif ext in (".docx", ".doc"):
        return header.startswith(b"PK\x03\x04") or header.startswith(b"\xd0\xcf\x11\xe0")
    elif ext in (".txt", ".md", ".csv", ".json", ".htm", ".html", ".eml", ".msg"):
        try:
            header.decode("utf-8", errors="strict")
            return True
        except UnicodeDecodeError:
            return False
    return True


# ---------------------------------------------------------------------------
# HIERARCHICAL & VERSIONED CORPORATE CONTRACT & POLICY GRAPH FIXTURES
# ---------------------------------------------------------------------------
SEED_COMMERCIAL_FIXTURES: list[dict[str, Any]] = [
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement",
        "domain": "Procurement & Invoicing",
        "title": "Acme MSA: Payment Terms and Invoicing Schedule",
        "section": "Section 4.1",
        "parent_section": "Article IV",
        "hierarchy_level": "clause",
        "definitions_ref": "Section 1.1",
        "exceptions_ref": "Section 4.2",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 4.1 Payment Terms: Customer shall pay all undisputed invoice amounts within thirty (30) days "
            "of the invoice date ('Net 30'). All payments shall be made in U.S. Dollars via automated clearing house (ACH) "
            "or wire transfer to the account designated by Vendor. If Customer disputes any invoiced charges in good faith, "
            "Customer must provide written notice of the dispute specifying the grounds thereof prior to the due date."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement",
        "domain": "Procurement & Invoicing",
        "title": "Acme MSA: Late Payment Penalties and Interest Remedies",
        "section": "Section 4.2",
        "parent_section": "Section 4.1",
        "hierarchy_level": "subclause",
        "definitions_ref": "Section 1.1",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 4.2 Late Payment Penalties: Any undisputed amounts not received by Vendor within fifteen (15) days "
            "following the Net 30 due date shall accrue late interest at the rate of one and one-half percent (1.5%) per month, "
            "or the maximum legal rate permitted by applicable law, whichever is less. In addition to late interest, Vendor may "
            "suspend cloud service access upon ten (10) business days prior written notice if delinquent amounts remain unpaid."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement",
        "domain": "Risk & Indemnification",
        "title": "Acme MSA: Mutual Limitation of Liability Cap",
        "section": "Section 10.1",
        "parent_section": "Article X",
        "hierarchy_level": "clause",
        "exceptions_ref": "Section 10.2",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 10.1 Limitation of Liability: Except for obligations under Section 10.2 (Carve-outs), each party's maximum "
            "aggregate liability arising out of or related to this Agreement shall be limited to the total fees paid or payable by Customer "
            "to Vendor in the twelve (12) months preceding the incident giving rise to liability. Neither party shall be liable for lost profits, "
            "special, indirect, incidental, or consequential damages."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement",
        "domain": "Risk & Indemnification",
        "title": "Acme MSA: Uncapped Liability Carve-Out Exceptions",
        "section": "Section 10.2",
        "parent_section": "Section 10.1",
        "hierarchy_level": "carve_out",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 10.2 Liability Carve-Outs: The limitations and exclusions in Section 10.1 shall NOT apply to: "
            "(a) a party's breach of confidentiality obligations under Article VII; (b) a party's indemnification obligations "
            "under Section 11 (Third-Party IP Infringement); (c) damages caused by gross negligence or willful misconduct; or "
            "(d) Customer's payment obligations for services rendered."
        )
    },
    {
        "organization": "CloudScale AI",
        "counterparty": "Acme Corp",
        "agreement_type": "Service Level Agreement",
        "domain": "Service Levels & Operations",
        "title": "CloudScale SLA: Monthly System Availability Commitment",
        "section": "Exhibit B (SLA) Section 2.1",
        "parent_section": "Exhibit B",
        "hierarchy_level": "sla_metric",
        "exceptions_ref": "Exhibit B (SLA) Section 2.2",
        "authority_class": "amendment_addendum",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://cloudscale.ai/legal/sla-tier1.pdf",
        "content": (
            "Exhibit B Section 2.1 Availability Commitment: Vendor warrants that the core Cloud Services production platform "
            "shall achieve a Monthly Uptime Percentage of at least 99.9% during each calendar month of the subscription term. "
            "System availability is monitored continuously via automated external health probes recording HTTP 200 response codes."
        )
    },
    {
        "organization": "CloudScale AI",
        "counterparty": "Acme Corp",
        "agreement_type": "Service Level Agreement",
        "domain": "Service Levels & Operations",
        "title": "CloudScale SLA: Scheduled Maintenance Exclusions",
        "section": "Exhibit B (SLA) Section 2.2",
        "parent_section": "Exhibit B (SLA) Section 2.1",
        "hierarchy_level": "carve_out",
        "authority_class": "amendment_addendum",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://cloudscale.ai/legal/sla-tier1.pdf",
        "content": (
            "Exhibit B Section 2.2 Maintenance Exclusions: Monthly Uptime Percentage calculations exclude downtime resulting from: "
            "(a) scheduled maintenance conducted during the standard weekly maintenance window (Sundays 01:00-05:00 UTC) with at least "
            "forty-eight (48) hours advance written notice; (b) emergency security patching; or (c) Customer network misconfiguration or force majeure."
        )
    },
    {
        "organization": "CloudScale AI",
        "counterparty": "Acme Corp",
        "agreement_type": "Service Level Agreement",
        "domain": "Service Levels & Operations",
        "title": "CloudScale SLA: Service Credit Remedy Matrix",
        "section": "Exhibit B (SLA) Section 2.3",
        "parent_section": "Exhibit B",
        "hierarchy_level": "penalty",
        "authority_class": "amendment_addendum",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://cloudscale.ai/legal/sla-tier1.pdf",
        "content": (
            "Exhibit B Section 2.3 Service Credits: If Vendor fails to meet the 99.9% availability commitment, Customer's sole and "
            "exclusive remedy shall be receipt of service credits applied to subsequent invoices as follows: (i) 99.0% to 99.89%: 10% credit "
            "of monthly subscription fee; (ii) 95.0% to 98.99%: 25% credit; (iii) less than 95.0%: 50% credit. Claims must be submitted within thirty (30) days."
        )
    },
    {
        "organization": "Global Infosec Standard",
        "counterparty": "Acme Corp",
        "agreement_type": "Data Protection Addendum",
        "domain": "Security & Data Privacy",
        "title": "Global DPA: Security Controls and SOC2 Type II Certification",
        "section": "Exhibit C (DPA) Section 3.1",
        "parent_section": "Exhibit C",
        "hierarchy_level": "clause",
        "authority_class": "corporate_policy",
        "effective_date": datetime(2024, 6, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://security.acmecorp.internal/policies/dpa_soc2_standard.pdf",
        "content": (
            "Exhibit C Section 3.1 Security Standards: Vendor shall maintain an information security program meeting or exceeding "
            "the standards of AICPA SOC 2 Type II (Security, Availability, and Confidentiality). Vendor shall provide Customer with a "
            "copy of its current annual SOC 2 Type II independent auditor's report upon written request, subject to standard non-disclosure obligations."
        )
    },
    {
        "organization": "Global Infosec Standard",
        "counterparty": "Acme Corp",
        "agreement_type": "Data Protection Addendum",
        "domain": "Security & Data Privacy",
        "title": "Global DPA: 24-Hour Security Incident and Breach Notification",
        "section": "Exhibit C (DPA) Section 3.4",
        "parent_section": "Exhibit C",
        "hierarchy_level": "clause",
        "authority_class": "corporate_policy",
        "effective_date": datetime(2024, 6, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://security.acmecorp.internal/policies/dpa_soc2_standard.pdf",
        "content": (
            "Exhibit C Section 3.4 Security Incident Notification: In the event of confirmed unauthorized access, acquisition, or disclosure "
            "of Customer Data or Personal Data (a 'Security Incident'), Vendor shall notify Customer via email and telephone within twenty-four (24) "
            "hours of becoming aware. Vendor shall take immediate remediation steps and provide prompt daily status briefings."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "Internal Governance",
        "agreement_type": "Corporate Bylaws",
        "domain": "Corporate Governance & Delegated Authority",
        "title": "Acme Bylaws: Executive Expenditure Approval Authority Thresholds",
        "section": "Article IV Section 4.3",
        "parent_section": "Article IV",
        "hierarchy_level": "clause",
        "authority_class": "corporate_policy",
        "effective_date": datetime(2024, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://governance.acmecorp.internal/bylaws_2024.pdf",
        "content": (
            "Article IV Section 4.3 Delegated Authority Thresholds: Operational commitments, contracts, and purchase orders are subject "
            "to signature authorization limits: (a) Department Directors: up to $50,000 USD; (b) Vice Presidents: up to $250,000 USD; "
            "(c) Chief Executive Officer or Chief Financial Officer: up to $1,000,000 USD. Any commercial commitment exceeding $1,000,000 USD "
            "requires formal resolution and approval by the Board of Directors."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "Metropolitan Office Towers LLC",
        "agreement_type": "Commercial Lease",
        "domain": "Real Estate & Leasing",
        "title": "Commercial Office Lease: Triple Net (NNN) Operating Expenses & CAM",
        "section": "Lease § 5.2",
        "parent_section": "Article V",
        "hierarchy_level": "clause",
        "exceptions_ref": "Lease § 5.4",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2023, 9, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://facilities.acmecorp.internal/leases/suite_400_master.pdf",
        "content": (
            "Lease Section 5.2 Operating Expenses and Common Area Maintenance (CAM): Tenant shall pay as Additional Rent its Pro Rata Share (14.2%) "
            "of the Building's annual Operating Expenses and Common Area Maintenance costs. Operating Expenses exclude capital expenditures, "
            "mortgage interest, depreciation, and leasing commissions incurred for prospective tenants."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "Metropolitan Office Towers LLC",
        "agreement_type": "Commercial Lease",
        "domain": "Real Estate & Leasing",
        "title": "Commercial Office Lease: Annual Expense Audit Rights",
        "section": "Lease § 5.4",
        "parent_section": "Lease § 5.2",
        "hierarchy_level": "clause",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2023, 9, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://facilities.acmecorp.internal/leases/suite_400_master.pdf",
        "content": (
            "Lease Section 5.4 CAM Audit Rights: Within ninety (90) days following receipt of Landlord's annual year-end CAM reconciliation statement, "
            "Tenant shall have the right, upon ten (10) business days prior written notice, to examine and audit Landlord's books and records relating "
            "to Operating Expenses. If the audit discovers an overcharge exceeding five percent (5%), Landlord shall reimburse Tenant the full cost of the audit."
        )
    },
    # --- NEGATIVE DISTRACTOR / SUPERSEDED AGREEMENT FIXTURE ---
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement (Old 2021 Version)",
        "domain": "Procurement & Invoicing",
        "title": "Acme MSA (2021 Expired): Payment Terms and 90-Day Grace",
        "section": "Section 2021-MSA-4.1",
        "parent_section": "Article IV",
        "hierarchy_level": "clause",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2021, 1, 1),
        "expiration_date": datetime(2024, 12, 31),
        "superseded": True,
        "terminated": True,
        "superseded_by": "2025 Master Services Agreement (Section 4.1)",
        "source_url": "https://archive.acmecorp.internal/contracts/old_msa_2021.pdf",
        "content": (
            "SUPERSEDED AND INOPERATIVE: Customer shall remit payments within ninety (90) days of invoice date ('Net 90'). "
            "No late penalties or interest shall apply during the first ninety days following invoice submission. "
            "[EXPIRED DECEMBER 31, 2024 — SUPERSEDED BY 2025 MSA]."
        )
    }
]


def ingest_mock_data(db: Session, tenant_id: str = "org_default") -> dict[str, Any]:
    """
    Seed hierarchical, versioned corporate contract & policy graph fixtures into database.
    Populates:
      1. Relational Agreements table
      2. Clauses table with extracted structured slots
      3. Agreement Relations table (AMENDS, SUPERSEDES, INCORPORATES)
      4. Denormalized CommercialClauseVector table for hybrid retrieval
    """
    inserted = 0
    skipped = 0

    to_embed_texts = []
    to_insert_records = []

    # Map of agreement_title -> Agreement object
    agreements_map: dict[str, Agreement] = {}

    for item in SEED_COMMERCIAL_FIXTURES:
        content = item["content"]
        source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = db.query(CommercialClauseVector.id).filter(
            CommercialClauseVector.section == item["section"],
            CommercialClauseVector.organization == item["organization"],
            CommercialClauseVector.agreement_type == item["agreement_type"]
        ).first()

        if existing:
            skipped += 1
            continue

        to_embed_texts.append(content)
        to_insert_records.append((item, source_hash))

    if to_embed_texts:
        logger.info(f"Generating embeddings for {len(to_embed_texts)} demo contract fixtures...")
        vectors = get_embeddings_batch(to_embed_texts)

        for (item, source_hash), vec in zip(to_insert_records, vectors):
            topic, extracted_slots = extract_structured_slots(item["content"])

            # 1. Ensure Agreement instrument exists in relational graph
            ag_title = f"{item['organization']} - {item['agreement_type']}"
            if ag_title not in agreements_map:
                existing_ag = db.query(Agreement).filter(
                    Agreement.title == ag_title,
                    Agreement.tenant_id == tenant_id
                ).first()
                if not existing_ag:
                    inst_type = "master_services_agreement"
                    ag_type_lower = item["agreement_type"].lower()
                    if "sla" in ag_type_lower or "service level" in ag_type_lower:
                        inst_type = "service_level_agreement"
                    elif "dpa" in ag_type_lower or "data protection" in ag_type_lower:
                        inst_type = "data_processing_agreement"
                    elif "lease" in ag_type_lower:
                        inst_type = "commercial_lease"
                    elif "bylaw" in ag_type_lower:
                        inst_type = "bylaws"

                    ag_status = "superseded" if item.get("superseded") else "active"
                    new_ag = Agreement(
                        tenant_id=tenant_id,
                        title=ag_title,
                        instrument_type=inst_type,
                        counterparty=item.get("counterparty"),
                        effective_date=item.get("effective_date"),
                        expiration_date=item.get("expiration_date"),
                        status=ag_status,
                        source_filename=item.get("source_url"),
                    )
                    db.add(new_ag)
                    db.flush()
                    agreements_map[ag_title] = new_ag
                else:
                    agreements_map[ag_title] = existing_ag

            agreement_obj = agreements_map[ag_title]

            # 2. Add relational Clause
            relational_clause = Clause(
                tenant_id=tenant_id,
                agreement_id=agreement_obj.id,
                section=item["section"],
                title=item["title"],
                topic=topic,
                hierarchy_level=item.get("hierarchy_level", "clause"),
                authority_class=item.get("authority_class", "governing_agreement"),
                content=item["content"],
                structured_slots=extracted_slots,
                chunk_index=0,
                is_active=not item.get("superseded", False),
                embedding=vec
            )
            db.add(relational_clause)

            # 3. Add flat CommercialClauseVector for fast hybrid search
            flat_record = CommercialClauseVector(
                tenant_id=tenant_id,
                organization=item["organization"],
                counterparty=item.get("counterparty"),
                agreement_type=item["agreement_type"],
                domain=item.get("domain"),
                title=item["title"],
                section=item["section"],
                parent_section=item.get("parent_section"),
                hierarchy_level=item.get("hierarchy_level", "clause"),
                definitions_ref=item.get("definitions_ref"),
                exceptions_ref=item.get("exceptions_ref"),
                authority_class=item.get("authority_class", "governing_agreement"),
                effective_date=item.get("effective_date"),
                expiration_date=item.get("expiration_date"),
                amended_date=item.get("amended_date"),
                superseded=item.get("superseded", False),
                terminated=item.get("terminated", False),
                superseded_by=item.get("superseded_by"),
                source_url=item.get("source_url"),
                content=item["content"],
                source_header=f"[{item['agreement_type']}] {item['title']}",
                source_hash=source_hash,
                chunk_index=0,
                is_substantive=True,
                structured_slots=extracted_slots,
                embedding=vec
            )
            db.add(flat_record)
            inserted += 1

        # 4. Create explicit AgreementRelations (Graph Edges)
        msa_2025 = agreements_map.get("Acme Corp - Master Services Agreement")
        msa_2021 = agreements_map.get("Acme Corp - Master Services Agreement (Old 2021 Version)")
        sla_2025 = agreements_map.get("CloudScale AI - Service Level Agreement")
        dpa_2024 = agreements_map.get("Global Infosec Standard - Data Protection Addendum")

        if msa_2025 and msa_2021:
            rel = AgreementRelation(
                tenant_id=tenant_id,
                source_agreement_id=msa_2025.id,
                target_agreement_id=msa_2021.id,
                relation_type="SUPERSEDES",
                effective_date=datetime(2025, 1, 1),
                clause_scope="ALL",
                notes="2025 MSA completely supersedes the expired 2021 MSA."
            )
            db.add(rel)

        if sla_2025 and msa_2025:
            rel = AgreementRelation(
                tenant_id=tenant_id,
                source_agreement_id=sla_2025.id,
                target_agreement_id=msa_2025.id,
                relation_type="INCORPORATES",
                effective_date=datetime(2025, 1, 1),
                clause_scope="ALL",
                notes="CloudScale SLA is incorporated into the Acme MSA as Exhibit B."
            )
            db.add(rel)

        if dpa_2024 and msa_2025:
            rel = AgreementRelation(
                tenant_id=tenant_id,
                source_agreement_id=dpa_2024.id,
                target_agreement_id=msa_2025.id,
                relation_type="INCORPORATES",
                effective_date=datetime(2024, 6, 1),
                clause_scope="ALL",
                notes="Global DPA is incorporated into the Acme MSA as Exhibit C."
            )
            db.add(rel)

        db.commit()

    logger.info(f"Mock contract ingestion completed: {inserted} inserted, {skipped} skipped.")
    return {"inserted": inserted, "skipped": skipped, "total_records": inserted + skipped}


def ingest_business_document(
    file_path: str,
    deal_id: int | None = None,
    doc_type: str = "contract",
    organization: str = "Acme Corp",
    tenant_id: str = "org_default",
    db: Session | None = None
) -> dict[str, Any]:
    """
    Ingest a corporate contract or deal document with transactional safety,
    MIME magic byte validation, slot extraction, and DOS protection.
    """
    abs_path = os.path.abspath(file_path)
    allowed_dirs = settings.allowed_ingest_dirs_list
    if not any(abs_path == d or abs_path.startswith(d + os.sep) for d in allowed_dirs):
        raise ValueError(
            f"Security Exception: Ingestion path '{file_path}' is outside permitted directory boundaries ({settings.ALLOWED_INGEST_DIRS})."
        )

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Document file not found at: {file_path}")

    start_time = time.time()
    filename = os.path.basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    # 1. MIME Magic byte validation
    if not validate_file_magic_bytes(abs_path, ext):
        raise ValueError(f"MIME verification failure: File header does not match declared extension '{ext}'.")

    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    # 2. Compute file hash
    with open(abs_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    job_id = str(uuid.uuid4())
    job = IngestJob(
        id=job_id,
        tenant_id=tenant_id,
        file_path=abs_path,
        raw_file_hash=file_hash,
        status="running",
        stage="parsing",
    )
    db.add(job)
    db.commit()

    try:
        # 3. Parse Document
        job.stage = "parsing"
        db.commit()
        parsed_doc = parse_document(abs_path)
        if not parsed_doc or not parsed_doc.pages:
            raise ValueError(f"No text extracted from document '{filename}'")

        # 4. Chunk Document
        job.stage = "chunking"
        job.total_pages = parsed_doc.total_pages
        db.commit()
        chunks = chunk_document(parsed_doc)

        if len(chunks) > MAX_INGEST_CHUNKS_PER_DOC:
            raise ValueError(
                f"DOS Protection: Document generated {len(chunks)} chunks, exceeding max limit ({MAX_INGEST_CHUNKS_PER_DOC})."
            )

        job.chunks_total = len(chunks)
        job.stage = "extracting_slots"
        db.commit()

        # 5. Extract structured slots & prepare records
        batch_chunks = []
        for ch in chunks:
            ch_hash = hashlib.sha256(ch.text.encode("utf-8")).hexdigest()
            exists = db.query(CommercialClauseVector.id).filter(
                CommercialClauseVector.source_hash == ch_hash,
                CommercialClauseVector.tenant_id == tenant_id
            ).first()

            if not exists:
                topic, slots = extract_structured_slots(ch.text)
                batch_chunks.append({
                    "content": ch.text,
                    "section": ch.section_locator or "Section",
                    "chunk_index": ch.chunk_index,
                    "page_number": ch.page_number,
                    "source_hash": ch_hash,
                    "topic": topic,
                    "slots": slots
                })

        inserted = 0
        if batch_chunks:
            job.stage = "embedding"
            db.commit()
            texts = [c["content"] for c in batch_chunks]
            vectors = get_embeddings_batch(texts)
            job.chunks_embedded = len(vectors)

            # Relational Agreement record
            ag_title = f"{organization} - {filename}"
            ag_record = Agreement(
                tenant_id=tenant_id,
                title=ag_title,
                instrument_type=doc_type.lower(),
                counterparty=None,
                status="active",
                source_filename=filename,
                raw_hash=file_hash
            )
            db.add(ag_record)
            db.flush()

            for c, vec in zip(batch_chunks, vectors):
                # Relational Clause
                cl_record = Clause(
                    tenant_id=tenant_id,
                    agreement_id=ag_record.id,
                    section=c["section"],
                    title=f"{filename} - {c['section']}",
                    topic=c["topic"],
                    hierarchy_level="clause",
                    authority_class="statement_of_work" if "sow" in filename.lower() else "governing_agreement",
                    content=c["content"],
                    structured_slots=c["slots"],
                    chunk_index=c["chunk_index"],
                    is_active=True,
                    embedding=vec
                )
                db.add(cl_record)

                # Denormalized vector record
                flat_record = CommercialClauseVector(
                    tenant_id=tenant_id,
                    organization=organization,
                    counterparty=None,
                    agreement_type=doc_type.title(),
                    domain="Commercial Documentation",
                    title=filename,
                    section=c["section"],
                    parent_section=None,
                    hierarchy_level="clause",
                    authority_class="statement_of_work" if "sow" in filename.lower() else "governing_agreement",
                    content=c["content"],
                    source_header=f"[{filename}] {c['section']}",
                    source_hash=c["source_hash"],
                    chunk_index=c["chunk_index"],
                    is_substantive=True,
                    structured_slots=c["slots"],
                    embedding=vec
                )
                db.add(flat_record)
                inserted += 1

                if deal_id is not None:
                    ev_record = DealEvidence(
                        tenant_id=tenant_id,
                        deal_id=deal_id,
                        filename=filename,
                        doc_type=doc_type,
                        page_number=c["page_number"],
                        section_locator=c["section"],
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        embedding=vec
                    )
                    db.add(ev_record)

        job.status = "completed"
        job.stage = "indexed"
        job.inserted_records = inserted
        db.commit()

        elapsed = time.time() - start_time
        return {
            "status": "completed",
            "job_id": job_id,
            "file_path": abs_path,
            "filename": filename,
            "file_hash": file_hash,
            "deal_id": deal_id,
            "doc_type": doc_type,
            "pages_in": parsed_doc.total_pages,
            "chunks_out": len(chunks),
            "records_inserted": inserted,
            "duration_ms": round(elapsed * 1000, 2)
        }
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        db.commit()
        raise
    finally:
        if own_session:
            db.close()


def ingest_uploaded_business_file(
    file,
    deal_id: int | None = None,
    doc_type: str = "contract",
    organization: str = "Acme Corp",
    tenant_id: str = "org_default",
    db: Session | None = None
) -> dict[str, Any]:
    """Handle multipart file upload for business document ingestion."""
    import tempfile
    filename = getattr(file, "filename", "uploaded_doc")
    ext = os.path.splitext(filename)[1].lower()

    allowed_exts = {".pdf", ".docx", ".doc", ".eml", ".msg", ".txt", ".md", ".csv", ".htm", ".html"}
    if ext not in allowed_exts:
        raise ValueError(
            f"Unsupported document format '{ext}'. Supported formats: {', '.join(sorted(allowed_exts))}"
        )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name
        content = file.file.read() if hasattr(file, "file") else file.read()
        if len(content) > MAX_INGEST_FILE_SIZE_BYTES:
            os.remove(tmp_path)
            raise ValueError(f"File size exceeds maximum permitted limit ({MAX_INGEST_FILE_SIZE_BYTES // (1024*1024)}MB).")
        tmp.write(content)

    tmp_dir = os.path.dirname(tmp_path)
    if tmp_dir not in settings.extra_allowed_dirs:
        settings.extra_allowed_dirs.append(tmp_dir)

    try:
        report = ingest_business_document(
            file_path=tmp_path,
            deal_id=deal_id,
            doc_type=doc_type,
            organization=organization,
            tenant_id=tenant_id,
            db=db
        )
        report["filename"] = filename
        return report
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
