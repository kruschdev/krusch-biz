import hashlib
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .config import settings
from .db import CommercialClauseVector, DealEvidence, SessionLocal
from .rag import get_embeddings_batch

logger = logging.getLogger("kruschbiz.ingest")

# Maximum permitted file size for air-gapped sandboxed ingestion (50MB)
MAX_INGEST_FILE_SIZE_BYTES = 50 * 1024 * 1024

# ---------------------------------------------------------------------------
# HIERARCHICAL & VERSIONED CORPORATE CONTRACT & POLICY GRAPH FIXTURES
#
# Models real-world enterprise agreements:
#   Master Agreement -> Articles -> Clauses -> Subclauses -> SLA Metrics / Carve-Outs
# Includes temporal validity (effective dates, amendments) and authority classes.
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
        "title": "Acme MSA: Aggregate Limitation of Liability",
        "section": "Section 10.1",
        "parent_section": "Article X",
        "hierarchy_level": "clause",
        "definitions_ref": "Section 1.1",
        "exceptions_ref": "Section 10.2",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 10.1 Limitation of Liability: Except as expressly set forth in Section 10.2, each party's maximum aggregate "
            "liability arising out of or related to this Agreement, whether in contract, tort (including negligence), or otherwise, "
            "shall not exceed the total fees paid or payable by Customer in the twelve (12) month period immediately preceding the "
            "event giving rise to liability. In no event shall either party be liable for any lost profits, lost revenue, or consequential damages."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement",
        "domain": "Risk & Indemnification",
        "title": "Acme MSA: Carve-Outs to Limitation of Liability",
        "section": "Section 10.2",
        "parent_section": "Section 10.1",
        "hierarchy_level": "carve_out",
        "definitions_ref": "Section 1.1",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 10.2 Carve-outs and Exclusions: The liability limitations and damages waivers set forth in Section 10.1 shall "
            "NOT apply to: (a) a party's breach of its confidentiality obligations under Section 8; (b) indemnification obligations "
            "under Section 11; (c) damages resulting from a party's gross negligence, willful misconduct, or intentional fraud; or "
            "(d) Customer's obligation to pay all undisputed fees and charges when due."
        )
    },
    {
        "organization": "Acme Corp",
        "counterparty": "CloudScale AI",
        "agreement_type": "Master Services Agreement",
        "domain": "Risk & Indemnification",
        "title": "Acme MSA: Mutual Indemnification for Third-Party Claims",
        "section": "Section 11.1",
        "parent_section": "Article XI",
        "hierarchy_level": "clause",
        "definitions_ref": "Section 1.1",
        "authority_class": "governing_agreement",
        "effective_date": datetime(2025, 1, 1),
        "superseded": False,
        "terminated": False,
        "superseded_by": None,
        "source_url": "https://contracts.acmecorp.internal/agreements/msa_2025_cloudscale.pdf",
        "content": (
            "Section 11.1 Mutual Indemnification: Vendor shall defend, indemnify, and hold harmless Customer and its officers, "
            "directors, and employees against any third-party claims, suits, or proceedings alleging that Customer's authorized use "
            "of the Cloud Services infringes or misappropriates any valid United States patent, copyright, or trademark. Vendor's "
            "obligations are conditioned upon Customer providing prompt written notice, sole control of defense and settlement, and reasonable cooperation."
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


def ingest_mock_data(db: Session) -> dict[str, Any]:
    """Seed hierarchical, versioned corporate contract & policy graph fixtures into database."""
    inserted = 0
    skipped = 0

    to_embed_texts = []
    to_insert_records = []

    for item in SEED_COMMERCIAL_FIXTURES:
        content = item["content"]
        source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = db.query(CommercialClauseVector).filter(
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
            record = CommercialClauseVector(
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
                embedding=vec
            )
            db.add(record)
            inserted += 1

        db.commit()

    logger.info(f"Mock contract ingestion completed: {inserted} inserted, {skipped} skipped.")
    return {"inserted": inserted, "skipped": skipped, "total_records": inserted + skipped}


def ingest_business_document(
    file_path: str,
    deal_id: int | None = None,
    doc_type: str = "contract",
    organization: str = "Acme Corp",
    db: Session | None = None
) -> dict[str, Any]:
    """
    Ingest a corporate contract, deal exhibit, policy, or discovery document
    (PDF with OCR fallback, DOCX, EML, TXT, MD, CSV) using the KruschNexus parser and chunking engine.
    Populates CommercialClauseVector (for enterprise search) and DealEvidence (for isolated deal rooms).
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

    # Bridge to KruschNexus parser and chunking engine
    try:
        from krusch_nexus.chunking import chunk_document_pages
        from krusch_nexus.parsers import parse_document
    except ImportError:
        candidate_paths = [
            settings.KRUSCH_NEXUS_PATH,
            os.getenv("KRUSCH_NEXUS_PATH"),
            "/nexus/src",
            "/home/krusch/homelab/projects/krusch-nexus/src",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "krusch-nexus", "src"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "krusch-nexus", "src"),
        ]
        for p in candidate_paths:
            if p and os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)
                break
        from krusch_nexus.chunking import chunk_document_pages
        from krusch_nexus.parsers import parse_document

    parsed_doc = parse_document(abs_path, filename)
    if not parsed_doc or not parsed_doc.pages:
        raise ValueError(f"No text extracted from document '{filename}'")

    pages = parsed_doc.pages
    total_pages = len(pages)
    ocr_pages = [p.page_number for p in pages if getattr(p, "ocr_applied", False) and p.page_number is not None]

    file_hash = parsed_doc.file_hash
    if not file_hash:
        with open(abs_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

    chunks = chunk_document_pages(
        pages=pages,
        filename=filename,
        file_hash=file_hash,
        max_chars=2000,
        overlap_chars=150,
        base_metadata={"deal_id": deal_id, "doc_type": doc_type, "organization": organization}
    )

    own_session = False
    if db is None:
        db = SessionLocal()
        own_session = True

    inserted = 0
    try:
        batch_chunks = []
        for ch in chunks:
            exists = db.query(CommercialClauseVector.id).filter(CommercialClauseVector.source_hash == ch.source_hash).first()
            if not exists:
                header_display = ch.header or "Section"
                sec_str = ch.citation if getattr(ch, "citation", None) else (
                    f"p. {ch.page_number} § {header_display}" if ch.page_number is not None else f"§ {header_display}"
                )
                src_hdr = (
                    f"[{filename} - p.{ch.page_number}] {header_display}"
                    if ch.page_number is not None
                    else f"[{filename}] {header_display}"
                )
                batch_chunks.append({
                    "organization": organization,
                    "counterparty": None,
                    "agreement_type": doc_type.title(),
                    "domain": "Commercial Documentation",
                    "title": filename,
                    "section": sec_str,
                    "parent_section": None,
                    "hierarchy_level": "clause",
                    "authority_class": "statement_of_work" if "sow" in filename.lower() else "governing_agreement",
                    "content": ch.text,
                    "source_header": src_hdr,
                    "source_hash": ch.source_hash,
                    "chunk_index": ch.chunk_index,
                    "page_number": ch.page_number,
                })

        if batch_chunks:
            texts = [c["content"] for c in batch_chunks]
            vectors = get_embeddings_batch(texts)

            for c, vec in zip(batch_chunks, vectors):
                record = CommercialClauseVector(
                    organization=c["organization"],
                    counterparty=c["counterparty"],
                    agreement_type=c["agreement_type"],
                    domain=c["domain"],
                    title=c["title"],
                    section=c["section"],
                    parent_section=c["parent_section"],
                    hierarchy_level=c["hierarchy_level"],
                    authority_class=c["authority_class"],
                    content=c["content"],
                    source_header=c["source_header"],
                    source_hash=c["source_hash"],
                    chunk_index=c["chunk_index"],
                    is_substantive=True,
                    embedding=vec
                )
                db.add(record)
                inserted += 1

                # If associated with a deal matter, also store in isolated DealEvidence
                if deal_id is not None:
                    ev_record = DealEvidence(
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

            db.commit()

        elapsed = time.time() - start_time
        return {
            "status": "completed",
            "file_path": abs_path,
            "filename": filename,
            "file_hash": file_hash,
            "deal_id": deal_id,
            "doc_type": doc_type,
            "pages_in": total_pages,
            "ocr_pages": ocr_pages,
            "chunks_out": len(chunks),
            "records_inserted": inserted,
            "duration_ms": round(elapsed * 1000, 2)
        }
    finally:
        if own_session:
            db.close()


def ingest_uploaded_business_file(
    file,
    deal_id: int | None = None,
    doc_type: str = "contract",
    organization: str = "Acme Corp",
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
            db=db
        )
        report["filename"] = filename
        return report
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
