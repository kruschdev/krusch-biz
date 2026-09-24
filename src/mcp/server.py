#!/usr/bin/env python3
"""
KruschBiz Model Context Protocol (MCP) Server.
Exposes air-gapped corporate contract search, deal logging, KruschNexus ingestion,
and staged executive memorandum drafting to IDE agents via stdio JSON-RPC.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any

from ..backend.business_ocr import parse_business_document
from ..backend.business_templates import generate_commercial_document
from ..backend.db import (
    CommercialClauseVector,
    CommercialGroundingReport,
    ContractPortfolio,
    DealMatter,
    Invoice,
    SessionLocal,
)
from ..backend.ingest import ingest_business_document
from ..backend.rag import (
    generate_executive_brief,
    get_embedding,
    retrieve_clauses,
)

# Configure logging to stderr so stdio JSON-RPC on stdout remains clean
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [KruschBiz MCP] %(levelname)s: %(message)s"
)
logger = logging.getLogger("kruschbiz.mcp")


TOOLS_CATALOG = [
    {
        "name": "search_contracts_and_policies",
        "description": "Perform hybrid full-text and vector semantic search across enterprise contracts, MSAs, SLAs, NDAs, and corporate policies in the air-gapped KruschBiz store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Commercial inquiry or contractual terms (e.g., 'liability cap gross negligence', '99.9% SLA credit schedule')"
                },
                "organization": {
                    "type": "string",
                    "description": "Company or enterprise name (e.g., 'Acme Corp')"
                },
                "agreement_type": {
                    "type": "string",
                    "description": "Agreement classification (e.g., 'Master Services Agreement', 'Service Level Agreement')"
                },
                "domain": {
                    "type": "string",
                    "description": "Subject matter domain (e.g., 'Procurement & Invoicing', 'Risk & Indemnification')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of clauses to return (default: 5, max: 20)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_clause_details",
        "description": "Retrieve the unabridged text and metadata for a specific contractual section or clause.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Section identifier (e.g., 'Section 10.1' or 'Exhibit B Section 2.1')"
                },
                "organization": {
                    "type": "string",
                    "description": "Optional organization filter (e.g., 'Acme Corp')"
                }
            },
            "required": ["section"]
        }
    },
    {
        "name": "log_deal_matter",
        "description": "Log a confidential corporate deal, transaction, or vendor review into the air-gapped database with local dense embeddings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Descriptive title for the deal or transaction"
                },
                "context_facts": {
                    "type": "string",
                    "description": "Comprehensive narrative of facts, terms, counterparty proposals, and deal context"
                },
                "deal_code": {
                    "type": "string",
                    "description": "Internal transaction tracking code (e.g., 'DEAL-2026-081')"
                },
                "company_name": {
                    "type": "string",
                    "description": "Internal enterprise entity"
                },
                "counterparty_name": {
                    "type": "string",
                    "description": "Counterparty corporate entity"
                },
                "deal_type": {
                    "type": "string",
                    "description": "Deal classification (e.g., 'Vendor Procurement', 'SaaS Licensing', 'M&A Due Diligence')"
                }
            },
            "required": ["title", "context_facts"]
        }
    },
    {
        "name": "list_deal_matters",
        "description": "Enumerate active corporate deals, transactions, and matter codes in KruschBiz.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of deals to return (default: 10)",
                    "default": 10
                }
            }
        }
    },
    {
        "name": "draft_deal_brief",
        "description": "Stage a 4-part executive commercial memorandum with assertion-level grounding audit. REFUSES to draft if no relevant governing agreements exist in the corpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deal_id": {
                    "type": "integer",
                    "description": "Optional ID of an existing logged deal matter"
                },
                "context_facts": {
                    "type": "string",
                    "description": "Transaction background narrative and key deal points (required if deal_id not provided)"
                },
                "title": {
                    "type": "string",
                    "description": "Title of the transaction or executive memorandum"
                },
                "counterparty": {
                    "type": "string",
                    "description": "Counterparty corporate name"
                },
                "deal_code": {
                    "type": "string",
                    "description": "Internal deal code"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of governing clauses to retrieve for context",
                    "default": 5
                }
            }
        }
    },
    {
        "name": "get_grounding_audit",
        "description": "Retrieve the stored assertion-level proposition grounding audit for a specific deal matter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deal_id": {
                    "type": "integer",
                    "description": "Deal matter ID to inspect"
                }
            },
            "required": ["deal_id"]
        }
    },
    {
        "name": "ingest_business_document",
        "description": "Ingest an enterprise document (PDF, DOCX, EML, MD, TXT) via the KruschNexus citation spine into the corporate repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute filesystem path to the corporate document"
                },
                "deal_id": {
                    "type": "integer",
                    "description": "Optional deal ID to associate with as isolated deal room evidence"
                },
                "doc_type": {
                    "type": "string",
                    "description": "Document category (e.g. 'contract', 'redline', 'sla', 'policy')",
                    "default": "contract"
                },
                "organization": {
                    "type": "string",
                    "description": "Corporate organization name",
                    "default": "Acme Corp"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "resolve_controlling_clause",
        "description": "Traverse the commercial agreement relation graph (AMENDS, SUPERSEDES) to resolve which clause governs a topic as of a specific date.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "counterparty": {
                    "type": "string",
                    "description": "Counterparty or vendor name (e.g. 'CloudScale AI')"
                },
                "topic": {
                    "type": "string",
                    "description": "Canonical commercial topic (e.g. 'PAYMENT_TERMS', 'LIMITATION_OF_LIABILITY', 'SLA_PERFORMANCE')"
                },
                "as_of_date": {
                    "type": "string",
                    "description": "Optional ISO date (YYYY-MM-DD) for historical or point-in-time resolution"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Multi-tenant partition identifier",
                    "default": "org_default"
                }
            },
            "required": ["counterparty", "topic"]
        }
    },
    {
        "name": "detect_contract_conflicts",
        "description": "Detect conflicting numeric terms and slot discrepancies (e.g. Net 30 vs Net 45) across concurrently active instruments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "counterparty": {
                    "type": "string",
                    "description": "Counterparty or vendor name"
                },
                "as_of_date": {
                    "type": "string",
                    "description": "Optional ISO date (YYYY-MM-DD)"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Multi-tenant partition identifier",
                    "default": "org_default"
                }
            },
            "required": ["counterparty"]
        }
    },
    {
        "name": "diff_contract_instruments",
        "description": "Diff two legal instruments side-by-side to align clauses by topic, extract text diffs, and highlight diverging structured slots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agreement_a_id": {
                    "type": "integer",
                    "description": "Base Agreement ID (e.g. 2021 Master Agreement)"
                },
                "agreement_b_id": {
                    "type": "integer",
                    "description": "Target Agreement ID (e.g. 2025 Master Agreement or Amendment)"
                },
                "tenant_id": {
                    "type": "string",
                    "description": "Multi-tenant partition identifier",
                    "default": "org_default"
                }
            },
            "required": ["agreement_a_id", "agreement_b_id"]
        }
    },
    {
        "name": "register_vendor_contract",
        "description": "Register a commercial vendor contract in the corporate portfolio to track value, expiration dates, and auto-renewal alerts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract_name": {"type": "string", "description": "Name or title of the vendor agreement"},
                "vendor": {"type": "string", "description": "Vendor or counterparty corporate entity"},
                "contract_type": {"type": "string", "description": "Contract type (e.g. 'Vendor MSA', 'SaaS License', 'Consulting', 'Commercial Lease')", "default": "Vendor MSA"},
                "expiration_date": {"type": "string", "description": "Expiration date in ISO format (YYYY-MM-DD)"},
                "value": {"type": "number", "description": "Total or annual contract monetary value"},
                "auto_renew": {"type": "boolean", "description": "Whether the contract automatically renews", "default": False},
                "reminder_days": {"type": "string", "description": "Comma-separated alert thresholds in days (default: '30,60,90')", "default": "30,60,90"},
                "notes": {"type": "string", "description": "Operational notes or key terms"},
                "tenant_id": {"type": "string", "default": "org_default"}
            },
            "required": ["contract_name", "vendor"]
        }
    },
    {
        "name": "list_expiring_contracts",
        "description": "Enumerate vendor contracts in the portfolio that are expiring within a specified number of days.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "within_days": {"type": "integer", "description": "Lookahead window in days (default: 60)", "default": 60},
                "tenant_id": {"type": "string", "default": "org_default"}
            }
        }
    },
    {
        "name": "create_business_invoice",
        "description": "Generate a commercial client invoice with itemized line items, automated subtotal, tax rate calculation, and status tracking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string", "description": "Unique invoice tracking identifier (e.g. 'INV-2026-101')"},
                "client_name": {"type": "string", "description": "Client or customer corporate name"},
                "client_email": {"type": "string", "description": "Client contact billing email"},
                "line_items": {
                    "type": "array",
                    "description": "List of line items with description, quantity, and rate",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "quantity": {"type": "number", "default": 1.0},
                            "rate": {"type": "number"}
                        },
                        "required": ["description", "rate"]
                    }
                },
                "tax_rate": {"type": "number", "description": "Sales tax rate (e.g. 0.0825 for 8.25%)", "default": 0.0},
                "due_date": {"type": "string", "description": "Payment due date (YYYY-MM-DD)"},
                "notes": {"type": "string", "description": "Invoice payment instructions or wire details"},
                "tenant_id": {"type": "string", "default": "org_default"}
            },
            "required": ["invoice_number", "client_name"]
        }
    },
    {
        "name": "list_business_invoices",
        "description": "List commercial invoices or retrieve accounts receivable aging breakdown and overdue metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status_filter": {"type": "string", "description": "Filter by status: 'draft', 'sent', 'paid', 'overdue', 'cancelled'"},
                "include_receivables_summary": {"type": "boolean", "description": "Include AR aging buckets and total overdue metrics", "default": True},
                "tenant_id": {"type": "string", "default": "org_default"}
            }
        }
    },
    {
        "name": "generate_commercial_document",
        "description": "Draft standard commercial legal agreements (Mutual NDA, B2B MSA, Statement of Work, Independent Contractor Agreement, Demand for Payment) using verified KruschBiz templates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "string",
                    "enum": ["commercial_nda", "master_services_agreement", "statement_of_work", "independent_contractor", "commercial_demand_letter"],
                    "description": "Commercial template identifier"
                },
                "field_data": {
                    "type": "object",
                    "description": "Key-value dictionary of template variables"
                }
            },
            "required": ["template_id"]
        }
    },
    {
        "name": "parse_business_document_ocr",
        "description": "Parse an invoice, receipt, or contract file using structured OCR heuristics to extract vendor, line items, amounts, and dates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to document file on disk (PDF, PNG, JPG, TXT)"},
                "doc_type_hint": {"type": "string", "enum": ["invoice", "receipt", "contract", "auto"], "default": "auto"}
            },
            "required": ["file_path"]
        }
    }
]


def handle_search_contracts(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query", "").strip()
    limit = min(args.get("limit", 5), 20)
    org = args.get("organization")
    ag_type = args.get("agreement_type")
    domain = args.get("domain")

    db = SessionLocal()
    try:
        results = retrieve_clauses(
            db=db,
            query=query,
            limit=limit,
            organization=org,
            agreement_type=ag_type,
            domain=domain
        )
        return {
            "query": query,
            "total_found": len(results),
            "clauses": [
                {
                    "id": c.get("id"),
                    "organization": c.get("organization"),
                    "agreement_type": c.get("agreement_type"),
                    "section": c.get("section"),
                    "title": c.get("title"),
                    "hierarchy_level": c.get("hierarchy_level"),
                    "authority_class": c.get("authority_class"),
                    "content": c.get("content"),
                    "rrf_score": c.get("rrf_score")
                }
                for c in results
            ]
        }
    finally:
        db.close()


def handle_get_clause(args: dict[str, Any]) -> dict[str, Any]:
    sec = args.get("section", "").strip()
    org = args.get("organization")

    db = SessionLocal()
    try:
        q = db.query(CommercialClauseVector).filter(CommercialClauseVector.section.ilike(f"%{sec}%"))
        if org:
            q = q.filter(CommercialClauseVector.organization.ilike(f"%{org}%"))
        clause = q.first()
        if not clause:
            return {"status": "not_found", "message": f"Clause '{sec}' not found in KruschBiz corpus."}

        return {
            "status": "found",
            "clause": {
                "id": clause.id,
                "organization": clause.organization,
                "counterparty": clause.counterparty,
                "agreement_type": clause.agreement_type,
                "domain": clause.domain,
                "title": clause.title,
                "section": clause.section,
                "parent_section": clause.parent_section,
                "hierarchy_level": clause.hierarchy_level,
                "definitions_ref": clause.definitions_ref,
                "exceptions_ref": clause.exceptions_ref,
                "authority_class": clause.authority_class,
                "effective_date": str(clause.effective_date) if clause.effective_date else None,
                "superseded": clause.superseded,
                "content": clause.content
            }
        }
    finally:
        db.close()


def handle_log_deal(args: dict[str, Any]) -> dict[str, Any]:
    title = args.get("title", "").strip()
    facts = args.get("context_facts", "").strip()
    deal_code = args.get("deal_code")
    company = args.get("company_name", "Acme Corp")
    counterparty = args.get("counterparty_name")
    deal_type = args.get("deal_type", "Commercial Agreement")

    if not title or not facts:
        return {"error": "Both 'title' and 'context_facts' are required."}

    vec = None
    try:
        vec = get_embedding(f"{title} {facts}")
    except Exception as e:
        logger.warning(f"Could not generate embedding for deal log: {e}")

    db = SessionLocal()
    try:
        deal = DealMatter(
            title=title,
            context_facts=facts,
            deal_code=deal_code,
            company_name=company,
            counterparty_name=counterparty,
            deal_type=deal_type,
            status="active",
            embedding=vec
        )
        db.add(deal)
        db.commit()
        db.refresh(deal)
        return {
            "status": "created",
            "deal_id": deal.id,
            "deal_code": deal.deal_code,
            "title": deal.title,
            "created_at": str(deal.created_at)
        }
    finally:
        db.close()


def handle_list_deals(args: dict[str, Any]) -> dict[str, Any]:
    limit = min(args.get("limit", 10), 50)
    db = SessionLocal()
    try:
        deals = db.query(DealMatter).filter(
            DealMatter.is_deleted == False
        ).order_by(DealMatter.created_at.desc()).limit(limit).all()
        return {
            "total": len(deals),
            "deals": [
                {
                    "id": d.id,
                    "deal_code": d.deal_code,
                    "company_name": d.company_name,
                    "counterparty_name": d.counterparty_name,
                    "deal_type": d.deal_type,
                    "title": d.title,
                    "status": d.status,
                    "created_at": str(d.created_at)
                }
                for d in deals
            ]
        }
    finally:
        db.close()


def handle_draft_brief(args: dict[str, Any]) -> dict[str, Any]:
    deal_id = args.get("deal_id")
    facts = args.get("context_facts")
    title = args.get("title")
    counterparty = args.get("counterparty")
    deal_code = args.get("deal_code")
    limit = min(args.get("limit", 5), 15)

    db = SessionLocal()
    try:
        if deal_id is not None:
            deal = db.query(DealMatter).filter(DealMatter.id == deal_id).first()
            if not deal:
                return {"error": f"Deal #{deal_id} not found."}
            title = title or deal.title
            facts = facts or deal.context_facts
            counterparty = counterparty or deal.counterparty_name
            deal_code = deal_code or deal.deal_code

        if not facts:
            return {"error": "Context facts are required to draft an executive brief."}

        title = title or "Commercial Deal Analysis"
        search_query = f"{title} {facts}"

        clauses = retrieve_clauses(db=db, query=search_query, limit=limit)
        if not clauses:
            return {
                "status": "refused",
                "error_code": "CANNOT_DRAFT_WITHOUT_AUTHORITIES",
                "message": "KruschBiz strictly refuses to draft an executive brief when zero governing agreements or commercial policies are found in the corpus."
            }

        brief_text, stats, claim_records = generate_executive_brief(
            deal_title=title,
            context_facts=facts,
            clauses=clauses,
            deal_code=deal_code,
            counterparty=counterparty,
            deal_id=deal_id,
            db=db
        )

        if stats.get("refusal_reason"):
            return {
                "status": "refused",
                "error_code": stats["refusal_reason"],
                "message": brief_text,
                "conflict_details": stats.get("conflict_details")
            }

        return {
            "status": "drafted",
            "review_required": True,
            "provisional_work_product": True,
            "deal_title": title,
            "brief": brief_text,
            "grounding_pass_rate": stats.get("pass_rate", 0),
            "claims_audited": len(claim_records)
        }
    finally:
        db.close()


def handle_get_grounding_audit(args: dict[str, Any]) -> dict[str, Any]:
    deal_id = args.get("deal_id")
    if not deal_id:
        return {"error": "deal_id is required."}

    db = SessionLocal()
    try:
        report = db.query(CommercialGroundingReport).filter(
            CommercialGroundingReport.deal_id == deal_id
        ).order_by(CommercialGroundingReport.created_at.desc()).first()
        if not report:
            return {"status": "not_found", "message": f"No grounding reports found for Deal #{deal_id}."}

        return {
            "deal_id": deal_id,
            "pass_rate": report.pass_rate,
            "total_claims": report.total_claims,
            "supported_claims": report.supported_claims,
            "unsupported_claims": report.unsupported_claims,
            "invented_clauses": report.invented_clauses,
            "superseded_terms": report.superseded_terms,
            "claims_audit": json.loads(report.claims_json),
            "advisory_markdown": report.advisory_markdown
        }
    finally:
        db.close()


def handle_ingest_document(args: dict[str, Any]) -> dict[str, Any]:
    file_path = args.get("file_path", "").strip()
    deal_id = args.get("deal_id")
    doc_type = args.get("doc_type", "contract")
    org = args.get("organization", "Acme Corp")

    if not file_path:
        return {"error": "file_path is required."}

    db = SessionLocal()
    try:
        report = ingest_business_document(
            file_path=file_path,
            deal_id=deal_id,
            doc_type=doc_type,
            organization=org,
            db=db
        )
        return report
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def handle_resolve_controlling_clause(args: dict[str, Any]) -> dict[str, Any]:
    counterparty = args.get("counterparty", "").strip()
    topic = args.get("topic", "").strip()
    as_of = args.get("as_of_date")
    tenant_id = args.get("tenant_id", "org_default")
    if not counterparty or not topic:
        return {"error": "Both 'counterparty' and 'topic' are required."}

    from ..backend.resolver import resolve_controlling_clause
    from datetime import datetime
    parsed_date = None
    if as_of:
        try:
            parsed_date = datetime.fromisoformat(as_of)
        except ValueError:
            return {"error": "Invalid date format. Use ISO format (YYYY-MM-DD)."}

    db = SessionLocal()
    try:
        return resolve_controlling_clause(db, tenant_id, counterparty, topic, parsed_date)
    finally:
        db.close()


def handle_detect_conflicts(args: dict[str, Any]) -> dict[str, Any]:
    counterparty = args.get("counterparty", "").strip()
    as_of = args.get("as_of_date")
    tenant_id = args.get("tenant_id", "org_default")
    if not counterparty:
        return {"error": "'counterparty' is required."}

    from ..backend.resolver import detect_contract_conflicts
    from datetime import datetime
    parsed_date = None
    if as_of:
        try:
            parsed_date = datetime.fromisoformat(as_of)
        except ValueError:
            return {"error": "Invalid date format. Use ISO format (YYYY-MM-DD)."}

    db = SessionLocal()
    try:
        conflicts = detect_contract_conflicts(db, tenant_id, counterparty, parsed_date)
        return {"counterparty": counterparty, "conflicts": conflicts, "total_conflicts": len(conflicts)}
    finally:
        db.close()


def handle_diff_instruments(args: dict[str, Any]) -> dict[str, Any]:
    ag_a_id = args.get("agreement_a_id")
    ag_b_id = args.get("agreement_b_id")
    tenant_id = args.get("tenant_id", "org_default")
    if ag_a_id is None or ag_b_id is None:
        return {"error": "Both 'agreement_a_id' and 'agreement_b_id' are required."}

    from ..backend.resolver import diff_agreements
    db = SessionLocal()
    try:
        return diff_agreements(db, int(ag_a_id), int(ag_b_id), tenant_id)
    finally:
        db.close()


def handle_register_contract(args: dict[str, Any]) -> dict[str, Any]:
    c_name = args.get("contract_name", "").strip()
    vendor = args.get("vendor", "").strip()
    c_type = args.get("contract_type", "Vendor MSA")
    exp_date = args.get("expiration_date")
    val = args.get("value")
    auto_ren = args.get("auto_renew", False)
    rem_days = args.get("reminder_days", "30,60,90")
    notes = args.get("notes")
    tenant_id = args.get("tenant_id", "org_default")

    if not c_name or not vendor:
        return {"error": "Both 'contract_name' and 'vendor' are required."}

    exp_dt = None
    if exp_date:
        try:
            exp_dt = datetime.fromisoformat(exp_date)
        except ValueError:
            return {"error": "Invalid expiration_date format. Use YYYY-MM-DD."}

    db = SessionLocal()
    try:
        contract = ContractPortfolio(
            tenant_id=tenant_id,
            contract_name=c_name,
            vendor=vendor,
            contract_type=c_type,
            expiration_date=exp_dt,
            value=val,
            auto_renew=auto_ren,
            reminder_days=rem_days,
            notes=notes,
            status="active"
        )
        db.add(contract)
        db.commit()
        db.refresh(contract)
        return {
            "status": "success",
            "contract_id": contract.id,
            "contract_name": contract.contract_name,
            "vendor": contract.vendor,
            "expiration_date": contract.expiration_date.isoformat() if contract.expiration_date else None,
            "value": contract.value
        }
    finally:
        db.close()


def handle_list_expiring_contracts(args: dict[str, Any]) -> dict[str, Any]:
    within_days = int(args.get("within_days", 60))
    tenant_id = args.get("tenant_id", "org_default")

    db = SessionLocal()
    try:
        now = datetime.now()
        threshold = now + timedelta(days=within_days)
        contracts = db.query(ContractPortfolio).filter(
            ContractPortfolio.tenant_id == tenant_id,
            ContractPortfolio.status.in_(["active", "expiring_soon"]),
            ContractPortfolio.expiration_date.isnot(None),
            ContractPortfolio.expiration_date <= threshold
        ).order_by(ContractPortfolio.expiration_date.asc()).all()

        results = []
        for c in contracts:
            days_left = (c.expiration_date.replace(tzinfo=None) - now).days
            results.append({
                "id": c.id,
                "contract_name": c.contract_name,
                "vendor": c.vendor,
                "expiration_date": c.expiration_date.strftime("%Y-%m-%d"),
                "days_left": days_left,
                "value": c.value,
                "auto_renew": c.auto_renew
            })
        return {
            "within_days": within_days,
            "total_expiring": len(results),
            "contracts": results
        }
    finally:
        db.close()


def handle_create_invoice(args: dict[str, Any]) -> dict[str, Any]:
    inv_num = args.get("invoice_number", "").strip()
    client_name = args.get("client_name", "").strip()
    client_email = args.get("client_email")
    line_items = args.get("line_items", [])
    tax_rate = float(args.get("tax_rate", 0.0))
    due_date_str = args.get("due_date")
    notes = args.get("notes")
    tenant_id = args.get("tenant_id", "org_default")

    if not inv_num or not client_name:
        return {"error": "Both 'invoice_number' and 'client_name' are required."}

    subtotal = 0.0
    items_dicts = []
    for itm in line_items:
        qty = float(itm.get("quantity", 1.0))
        rate = float(itm.get("rate", 0.0))
        amt = round(qty * rate, 2)
        items_dicts.append({
            "description": itm.get("description", "Item"),
            "quantity": qty,
            "rate": rate,
            "amount": amt
        })
        subtotal += amt

    subtotal = round(subtotal, 2)
    tax_amt = round(subtotal * tax_rate, 2)
    total = round(subtotal + tax_amt, 2)

    due_dt = None
    if due_date_str:
        try:
            due_dt = datetime.fromisoformat(due_date_str)
        except ValueError:
            return {"error": "Invalid due_date format. Use YYYY-MM-DD."}

    db = SessionLocal()
    try:
        inv = Invoice(
            tenant_id=tenant_id,
            invoice_number=inv_num,
            client_name=client_name,
            client_email=client_email,
            line_items=items_dicts,
            subtotal=subtotal,
            tax_rate=tax_rate,
            tax_amount=tax_amt,
            total=total,
            status="draft",
            invoice_date=datetime.now(),
            due_date=due_dt,
            notes=notes
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)
        return {
            "status": "success",
            "invoice_id": inv.id,
            "invoice_number": inv.invoice_number,
            "client_name": inv.client_name,
            "total": inv.total,
            "subtotal": inv.subtotal,
            "tax_amount": inv.tax_amount,
            "status_code": inv.status
        }
    finally:
        db.close()


def handle_list_invoices(args: dict[str, Any]) -> dict[str, Any]:
    status_filter = args.get("status_filter")
    include_summary = args.get("include_receivables_summary", True)
    tenant_id = args.get("tenant_id", "org_default")

    db = SessionLocal()
    try:
        q = db.query(Invoice).filter(Invoice.tenant_id == tenant_id)
        if status_filter:
            q = q.filter(Invoice.status == status_filter)
        invoices = q.order_by(Invoice.invoice_date.desc().nullslast()).all()

        inv_list = []
        total_outstanding = 0.0
        total_overdue = 0.0
        now = datetime.now()

        for inv in invoices:
            is_od = False
            if inv.due_date and inv.due_date.replace(tzinfo=None) < now and inv.status in ["draft", "sent"]:
                is_od = True
            elif inv.status == "overdue":
                is_od = True

            if inv.status in ["draft", "sent", "overdue"]:
                total_outstanding += inv.total
                if is_od:
                    total_overdue += inv.total

            inv_list.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "client_name": inv.client_name,
                "total": inv.total,
                "status": "overdue" if is_od else inv.status,
                "due_date": inv.due_date.strftime("%Y-%m-%d") if inv.due_date else None,
                "is_overdue": is_od
            })

        resp = {
            "total_invoices": len(inv_list),
            "invoices": inv_list
        }
        if include_summary:
            resp["receivables_summary"] = {
                "total_outstanding": round(total_outstanding, 2),
                "total_overdue": round(total_overdue, 2)
            }
        return resp
    finally:
        db.close()


def handle_generate_commercial_document(args: dict[str, Any]) -> dict[str, Any]:
    tmpl_id = args.get("template_id", "").strip()
    field_data = args.get("field_data", {})
    if not tmpl_id:
        return {"error": "'template_id' is required."}
    try:
        return generate_commercial_document(tmpl_id, field_data)
    except Exception as e:
        return {"error": str(e)}


def handle_parse_ocr(args: dict[str, Any]) -> dict[str, Any]:
    file_path = args.get("file_path", "").strip()
    doc_type_hint = args.get("doc_type_hint", "auto")
    if not file_path:
        return {"error": "'file_path' is required."}
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    try:
        with open(file_path, "rb") as f:
            content = f.read()
        return parse_business_document(content, os.path.basename(file_path), doc_type_hint)
    except Exception as e:
        return {"error": str(e)}


DISPATCHER = {
    "search_contracts_and_policies": handle_search_contracts,
    "get_clause_details": handle_get_clause,
    "log_deal_matter": handle_log_deal,
    "list_deal_matters": handle_list_deals,
    "draft_deal_brief": handle_draft_brief,
    "get_grounding_audit": handle_get_grounding_audit,
    "ingest_business_document": handle_ingest_document,
    "resolve_controlling_clause": handle_resolve_controlling_clause,
    "detect_contract_conflicts": handle_detect_conflicts,
    "diff_contract_instruments": handle_diff_instruments,
    "register_vendor_contract": handle_register_contract,
    "list_expiring_contracts": handle_list_expiring_contracts,
    "create_business_invoice": handle_create_invoice,
    "list_business_invoices": handle_list_invoices,
    "generate_commercial_document": handle_generate_commercial_document,
    "parse_business_document_ocr": handle_parse_ocr,
}


def run_stdio_server():
    """Run JSON-RPC stdio protocol loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS_CATALOG}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            handler = DISPATCHER.get(tool_name)
            if not handler:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found."}
                }
            else:
                try:
                    result = handler(tool_args)
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": json.dumps(result, indent=2)}
                            ]
                        }
                    }
                except Exception as ex:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32000, "message": str(ex)}
                    }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not implemented."}
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
