#!/usr/bin/env python3
"""
KruschBiz Model Context Protocol (MCP) Server.
Sovereign Corporate Intelligence Engine: exposes contract search, DAG graph-walk
resolver, deal matter logging, KruschNexus ingestion, and assertion grounding.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from ..backend.db import (
    CommercialGroundingReport,
    DealMatter,
    SessionLocal,
)
from ..backend.ingest import ingest_business_document
from ..backend.rag import (
    generate_executive_brief,
    get_embedding,
    retrieve_clauses,
    verify_commercial_grounding,
)
from ..backend.resolver import (
    detect_contract_conflicts,
    diff_agreements,
    resolve_controlling_clause,
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
        "name": "contract_intelligence",
        "description": "Unified commercial contract and policy intelligence. Actions: 'search' (hybrid vector+lexical search across enterprise agreements), 'get_clause' (retrieve full clause by section), 'resolve_controlling' (walk amendment/superseding DAG for operative clause as of date), 'detect_conflicts' (scan for diverging terms across operative instruments), 'diff_instruments' (side-by-side comparison of two agreements).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "get_clause", "resolve_controlling", "detect_conflicts", "diff_instruments"],
                    "description": "Action to perform"
                },
                "query": {"type": "string", "description": "Search query or commercial terms (for 'search')"},
                "section": {"type": "string", "description": "Section identifier, e.g. 'Section 10.1' (for 'get_clause')"},
                "counterparty": {"type": "string", "description": "Counterparty or vendor name (for 'resolve_controlling', 'detect_conflicts')"},
                "topic": {"type": "string", "description": "Canonical commercial topic, e.g. 'PAYMENT_TERMS', 'LIMITATION_OF_LIABILITY' (for 'resolve_controlling')"},
                "as_of_date": {"type": "string", "description": "Optional ISO date YYYY-MM-DD (for 'resolve_controlling', 'detect_conflicts')"},
                "agreement_a_id": {"type": "integer", "description": "Base Agreement ID (for 'diff_instruments')"},
                "agreement_b_id": {"type": "integer", "description": "Target Agreement ID (for 'diff_instruments')"},
                "organization": {"type": "string", "description": "Optional organization filter"},
                "agreement_type": {"type": "string", "description": "Optional agreement type filter"},
                "domain": {"type": "string", "description": "Optional subject domain"},
                "limit": {"type": "integer", "description": "Max results to return (default: 5)", "default": 5},
                "tenant_id": {"type": "string", "default": "org_default"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_deal",
        "description": "Manage confidential corporate deals, transactions, and due diligence matters. Actions: 'log' (persist and vectorize new deal matter), 'list' (enumerate active deals), 'audit' (retrieve assertion-level proposition grounding audit), 'draft_brief' (generate executive memorandum with strict grounding).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["log", "list", "audit", "draft_brief"],
                    "description": "Action to perform"
                },
                "deal_id": {"type": "integer", "description": "Deal matter ID (required for 'audit')"},
                "title": {"type": "string", "description": "Title of the deal or transaction (for 'log', 'draft_brief')"},
                "context_facts": {"type": "string", "description": "Background facts and deal terms (for 'log', 'draft_brief')"},
                "deal_code": {"type": "string", "description": "Internal transaction code, e.g. 'DEAL-2026-081' (for 'log')"},
                "company_name": {"type": "string", "description": "Internal enterprise entity (for 'log')"},
                "counterparty_name": {"type": "string", "description": "Counterparty corporate entity (for 'log')"},
                "deal_type": {"type": "string", "description": "Deal classification (for 'log')"},
                "organization": {"type": "string", "description": "Entity organization (for 'draft_brief')", "default": "Acme Corp"},
                "limit": {"type": "integer", "description": "Max deals to return (for 'list', default: 10)", "default": 10}
            },
            "required": ["action"]
        }
    },
    {
        "name": "ingest_contract",
        "description": "Ingest an enterprise contract into the sovereign contract graph via KruschNexus with natural legal boundary chunking. Actions: 'ingest_file'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["ingest_file"], "default": "ingest_file"},
                "file_path": {"type": "string", "description": "Absolute path to the contract document (PDF, DOCX, TXT, MD, CSV)"},
                "deal_id": {"type": "integer", "description": "Optional associated deal ID"},
                "doc_type": {"type": "string", "description": "Document classification (default: 'contract')", "default": "contract"},
                "organization": {"type": "string", "description": "Governing enterprise entity", "default": "Acme Corp"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "verify_grounding",
        "description": "Run assertion-level proposition grounding verification against governing contract authorities. Validates numeric slot claims, citation existence, and amendment supersession. Returns 4-way failure taxonomy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "description": "List of proposition claims to verify",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim_id": {"type": "string"},
                            "sentence": {"type": "string"},
                            "cited_authority": {"type": "string"},
                            "term": {"type": "string"},
                            "value": {"type": "string"}
                        },
                        "required": ["sentence", "cited_authority"]
                    }
                },
                "authorities": {
                    "type": "array",
                    "description": "List of governing clause authorities with section, content, and structured_slots",
                    "items": {"type": "object"}
                }
            },
            "required": ["claims", "authorities"]
        }
    }
]


# Handlers

def handle_search_contracts(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query", "").strip()
    limit = args.get("limit", 5)
    org = args.get("organization")
    ag_type = args.get("agreement_type")
    domain = args.get("domain")

    if not query:
        return {"error": "Query cannot be empty."}

    db = SessionLocal()
    try:
        clauses = retrieve_clauses(
            db=db,
            query=query,
            limit=limit,
            organization=org,
            agreement_type=ag_type,
            domain=domain
        )
        return {
            "query": query,
            "total_found": len(clauses),
            "results": [
                {
                    "clause_id": c.get("id"),
                    "agreement_title": c.get("agreement_title"),
                    "section": c.get("section"),
                    "topic": c.get("topic"),
                    "content": c.get("content"),
                    "authority_class": c.get("authority_class"),
                    "structured_slots": c.get("structured_slots"),
                    "score": round(c.get("score", 0.0), 3)
                }
                for c in clauses
            ]
        }
    finally:
        db.close()


def handle_get_clause(args: dict[str, Any]) -> dict[str, Any]:
    section = args.get("section", "").strip()
    if not section:
        return {"error": "Section identifier is required."}

    db = SessionLocal()
    try:
        from ..backend.db import Clause
        clause = db.query(Clause).filter(
            Clause.section.ilike(f"%{section}%"),
            Clause.is_active.is_(True)
        ).first()

        if not clause:
            return {"status": "not_found", "message": f"No active clause found matching '{section}'."}

        ag = clause.agreement
        return {
            "status": "found",
            "clause": {
                "id": clause.id,
                "agreement_id": clause.agreement_id,
                "agreement_title": ag.title if ag else "Unknown",
                "section": clause.section,
                "title": clause.title,
                "topic": clause.topic,
                "authority_class": clause.authority_class,
                "content": clause.content,
                "structured_slots": clause.structured_slots
            }
        }
    finally:
        db.close()


def handle_log_deal(args: dict[str, Any]) -> dict[str, Any]:
    title = args.get("title", "").strip()
    facts = args.get("context_facts", "").strip()
    code = args.get("deal_code", "").strip() or None
    co_name = args.get("company_name", "Acme Corp")
    cp_name = args.get("counterparty_name", "Counterparty")
    d_type = args.get("deal_type", "General Corporate")

    if not title or not facts:
        return {"error": "Both 'title' and 'context_facts' are required."}

    db = SessionLocal()
    try:
        emb = get_embedding(f"{title}\n{facts}")
        deal = DealMatter(
            title=title,
            context_facts=facts,
            deal_code=code,
            company_name=co_name,
            counterparty_name=cp_name,
            deal_type=d_type,
            embedding=emb,
            status="active"
        )
        db.add(deal)
        db.commit()
        db.refresh(deal)
        return {
            "status": "created",
            "deal_id": deal.id,
            "deal_code": deal.deal_code,
            "title": deal.title,
            "message": "Confidential corporate deal matter logged."
        }
    finally:
        db.close()


def handle_list_deals(args: dict[str, Any]) -> dict[str, Any]:
    limit = args.get("limit", 10)
    db = SessionLocal()
    try:
        deals = db.query(DealMatter).filter(
            DealMatter.is_deleted.is_(False)
        ).order_by(DealMatter.created_at.desc()).limit(limit).all()

        return {
            "total": len(deals),
            "deals": [
                {
                    "id": d.id,
                    "deal_code": d.deal_code,
                    "title": d.title,
                    "company_name": d.company_name,
                    "counterparty_name": d.counterparty_name,
                    "deal_type": d.deal_type,
                    "status": d.status,
                    "created_at": str(d.created_at)
                }
                for d in deals
            ]
        }
    finally:
        db.close()


def handle_draft_brief(args: dict[str, Any]) -> dict[str, Any]:
    title = args.get("title", "").strip()
    facts = args.get("context_facts", "").strip()
    deal_id = args.get("deal_id")
    org = args.get("organization", "Acme Corp")
    limit = args.get("limit", 5)

    if not title or not facts:
        return {"error": "Both 'title' and 'context_facts' are required."}

    db = SessionLocal()
    try:
        clauses = retrieve_clauses(
            db=db,
            query=f"{title} {facts}",
            limit=limit,
            organization=org,
            exclude_superseded=True
        )
        analysis_text, grounding_stats, claims_records = generate_executive_brief(
            deal_title=title,
            context_facts=facts,
            clauses=clauses,
            deal_id=deal_id,
            db=db
        )
        if grounding_stats.get("refusal_reason"):
            return {
                "status": "refused",
                "error_code": grounding_stats["refusal_reason"],
                "message": analysis_text
            }
        return {
            "status": "drafted",
            "brief": analysis_text,
            "grounding": grounding_stats,
            "claims": claims_records,
            "review_required": True
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def handle_audit_deal(args: dict[str, Any]) -> dict[str, Any]:
    deal_id = args.get("deal_id")
    if not deal_id:
        return {"error": "deal_id is required."}

    db = SessionLocal()
    try:
        report = db.query(CommercialGroundingReport).filter(
            CommercialGroundingReport.deal_id == deal_id
        ).order_by(CommercialGroundingReport.created_at.desc()).first()

        if not report:
            return {"status": "not_found", "message": f"No audit report found for deal ID {deal_id}."}

        return {
            "status": "found",
            "deal_id": deal_id,
            "overall_grounding_score": report.overall_grounding_score,
            "verified_claims_count": report.verified_claims_count,
            "total_claims_count": report.total_claims_count,
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

    db = SessionLocal()
    try:
        return resolve_controlling_clause(db, tenant_id, counterparty, topic, as_of)
    finally:
        db.close()


def handle_detect_conflicts(args: dict[str, Any]) -> dict[str, Any]:
    counterparty = args.get("counterparty", "").strip()
    as_of = args.get("as_of_date")
    tenant_id = args.get("tenant_id", "org_default")
    if not counterparty:
        return {"error": "'counterparty' is required."}

    db = SessionLocal()
    try:
        conflicts = detect_contract_conflicts(db, tenant_id, counterparty, as_of)
        return {"counterparty": counterparty, "conflicts": conflicts, "total_conflicts": len(conflicts)}
    finally:
        db.close()


def handle_diff_instruments(args: dict[str, Any]) -> dict[str, Any]:
    ag_a_id = args.get("agreement_a_id")
    ag_b_id = args.get("agreement_b_id")
    tenant_id = args.get("tenant_id", "org_default")
    if ag_a_id is None or ag_b_id is None:
        return {"error": "Both 'agreement_a_id' and 'agreement_b_id' are required."}

    db = SessionLocal()
    try:
        return diff_agreements(db, int(ag_a_id), int(ag_b_id), tenant_id)
    finally:
        db.close()


def handle_contract_intelligence(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action")
    if action == "search":
        return handle_search_contracts(args)
    elif action == "get_clause":
        return handle_get_clause(args)
    elif action == "resolve_controlling":
        return handle_resolve_controlling_clause(args)
    elif action == "detect_conflicts":
        return handle_detect_conflicts(args)
    elif action == "diff_instruments":
        return handle_diff_instruments(args)
    else:
        return {"error": f"Unknown action '{action}' for contract_intelligence."}


def handle_manage_deal(args: dict[str, Any]) -> dict[str, Any]:
    action = args.get("action")
    if action == "log":
        return handle_log_deal(args)
    elif action == "list":
        return handle_list_deals(args)
    elif action == "audit":
        return handle_audit_deal(args)
    elif action == "draft_brief":
        return handle_draft_brief(args)
    else:
        return {"error": f"Unknown action '{action}' for manage_deal."}


def handle_verify_grounding(args: dict[str, Any]) -> dict[str, Any]:
    text = args.get("analysis_text") or args.get("text") or ""
    authorities = args.get("authorities", [])
    claims_input = args.get("claims")
    if claims_input and not text:
        if isinstance(claims_input, list):
            text = " ".join(c.get("sentence", "") for c in claims_input if isinstance(c, dict))
    passed, claims, advisory, metrics = verify_commercial_grounding(text, authorities)
    return {
        "passed": passed,
        "claims": claims,
        "advisory": advisory,
        "metrics": metrics,
        "verified_count": metrics.get("supported_claims", 0),
        "overall_score": metrics.get("pass_rate", 0.0)
    }


DISPATCHER = {
    "contract_intelligence": handle_contract_intelligence,
    "manage_deal": handle_manage_deal,
    "ingest_contract": handle_ingest_document,
    "verify_grounding": handle_verify_grounding,
}


def handle_tools_list() -> dict[str, Any]:
    return {"tools": TOOLS_CATALOG}


def handle_tools_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in DISPATCHER:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Error: Tool '{name}' not found in KruschBiz catalog."}]
        }
    try:
        handler = DISPATCHER[name]
        result = handler(arguments or {})
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
        }
    except Exception as e:
        logger.exception(f"Unhandled error in tool handler '{name}': {e}")
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Internal execution error: {str(e)}"}]
        }


def process_json_rpc(line: str) -> str | None:
    try:
        req = json.loads(line)
    except json.JSONDecodeError:
        return json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    if method == "initialize":
        res = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "kruschbiz-mcp",
                "version": "0.2.0",
                "environment": "sovereign-local"
            }
        }
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": res})

    elif method == "tools/list":
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": handle_tools_list()})

    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": handle_tools_call(name, args)})

    elif method == "ping":
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {}})

    else:
        return json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not implemented."}
        })


def main():
    logger.info("Starting KruschBiz MCP Server in Sovereign Stdio JSON-RPC Mode...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        response = process_json_rpc(line)
        if response:
            sys.stdout.write(response + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
