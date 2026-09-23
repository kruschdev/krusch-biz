#!/usr/bin/env python3
"""
KruschBiz Model Context Protocol (MCP) Server.
Exposes air-gapped corporate contract search, deal logging, KruschNexus ingestion,
and staged executive memorandum drafting to IDE agents via stdio JSON-RPC.
"""

import json
import logging
import sys
from typing import Any

from ..backend.db import CommercialClauseVector, CommercialGroundingReport, DealMatter, SessionLocal
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
