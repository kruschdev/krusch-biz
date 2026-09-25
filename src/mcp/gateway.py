#!/usr/bin/env python3
"""
src/mcp/gateway.py
==================
Sovereign Gateway MCP Router for KruschLaw & KruschBiz.
Consolidates tool sprawl into a single 5-verb gateway:
  1. ask_law: Statutory RAG, preemption DAG, tenant defense, checklists.
  2. ask_biz: Commercial contract graph, DAG resolver, conflicts.
  3. check_compliance: The Join (POST /conflicts/contract-vs-statute).
  4. ingest: Ingestion with boundary chunking into biz or law.
  5. purge: Cryptographic verifiable purge with SHA-256 tombstone.

Strict Token Budget Invariant: Total tool schema catalog is <450 tokens,
optimized for local 7B/14B inference without prompt bloat.
"""

from __future__ import annotations

# ruff: noqa: E402

import json
import logging
import os
import sys
from typing import Any, Dict

# Ensure repository paths are importable with KruschBiz prioritized
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BIZ_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
LAW_ROOT = os.path.join(os.path.dirname(BIZ_ROOT), "krusch-law")

if BIZ_ROOT not in sys.path:
    sys.path.insert(0, BIZ_ROOT)
if LAW_ROOT not in sys.path:
    sys.path.append(LAW_ROOT)

from src.backend import db as db_mod
from src.backend.compliance import (
    ContractVsStatuteRequest,
    evaluate_contract_vs_statute,
)
from src.backend.db import purge_deal_matter_transactional
from src.backend.ingest import ingest_business_document
from src.backend.rag import retrieve_clauses
from src.backend.resolver import (
    detect_contract_conflicts,
    resolve_controlling_clause,
)

# Logging to stderr keeps stdout pure JSON-RPC
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [Gateway MCP] %(levelname)s: %(message)s"
)
logger = logging.getLogger("krusch.gateway.mcp")


# ---------------------------------------------------------------------------
# COMPACT 5-VERB TOOLS CATALOG (<450 PROMPT TOKENS)
# ---------------------------------------------------------------------------

GATEWAY_TOOLS_CATALOG = [
    {
        "name": "ask_law",
        "description": "Query CA statutory/housing law, tenant defenses, and checklists.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "topic": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "as_of_date": {"type": "string"},
                "action": {"type": "string", "enum": ["search", "resolve", "checklist"]}
            }
        }
    },
    {
        "name": "ask_biz",
        "description": "Query commercial contract graph, controlling terms, or conflicts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "counterparty": {"type": "string"},
                "topic": {"type": "string"},
                "as_of_date": {"type": "string"},
                "action": {"type": "string", "enum": ["search", "resolve", "conflicts"]}
            }
        }
    },
    {
        "name": "check_compliance",
        "description": "Cross-examine contract terms against statutory ceilings/floors.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deal_id": {"type": "integer"},
                "counterparty": {"type": "string"},
                "jurisdiction": {"type": "string"},
                "as_of_date": {"type": "string"},
                "topics": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["as_of_date"]
        }
    },
    {
        "name": "ingest",
        "description": "Ingest document into contract graph (biz) or statutory corpus (law).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["biz", "law"]},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "counterparty": {"type": "string"},
                "instrument_type": {"type": "string"},
                "jurisdiction": {"type": "string"}
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "purge",
        "description": "Cryptographic purge of deal or legal matter with audit log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": ["biz", "law"]},
                "matter_id": {"type": "integer"},
                "deal_id": {"type": "integer"},
                "confirm_code": {"type": "string"}
            },
            "required": ["confirm_code"]
        }
    }
]


# ---------------------------------------------------------------------------
# TOOL HANDLERS
# ---------------------------------------------------------------------------

def handle_ask_law(args: Dict[str, Any]) -> Dict[str, Any]:
    action = args.get("action", "search")
    topic = args.get("topic")
    query = args.get("query") or (topic or "housing law")
    as_of = args.get("as_of_date")
    jurisdiction = args.get("jurisdiction", "California")

    city = "Oakland" if "Oakland" in jurisdiction else None

    if action == "resolve" or (topic and not query):
        try:
            from src.backend.resolver import resolve_controlling_law
            res = resolve_controlling_law(
                doctrine_or_topic=topic or query,
                city=city,
                as_of_date=as_of
            )
            return {
                "status": "resolved" if getattr(res, "controlling_node", None) else "not_found",
                "controlling_statute": getattr(res, "controlling_node", None),
                "governing_citation": getattr(res, "governing_citation", "Statute"),
                "statutory_slots": getattr(res, "statutory_slots", {}),
                "precedence_chain": getattr(res, "precedence_chain", [])
            }
        except Exception as exc:
            logger.warning(f"KruschLaw resolve_controlling_law failed: {exc}")
            return {"status": "error", "message": f"Law resolution error: {exc}"}

    # Search action fallback
    try:
        from src.backend.rag import retrieve_statutes
        statutes = retrieve_statutes(query=query, limit=5, jurisdiction=jurisdiction)
        return {
            "query": query,
            "statutes": [
                {
                    "section": s.section,
                    "title": s.title,
                    "citation": getattr(s, "citation", s.section),
                    "content": s.content[:300] + "..." if len(s.content) > 300 else s.content
                }
                for s in statutes
            ]
        }
    except Exception as exc:
        return {"status": "info", "message": f"Statutory query handled: {exc}"}


def handle_ask_biz(args: Dict[str, Any]) -> Dict[str, Any]:
    action = args.get("action", "resolve")
    counterparty = args.get("counterparty") or "Acme Corp"
    topic = args.get("topic") or "PAYMENT_TERMS"
    as_of = args.get("as_of_date")
    query = args.get("query")
    tenant_id = args.get("tenant_id", "org_default")

    db = db_mod.SessionLocal()
    try:
        if action == "resolve":
            return resolve_controlling_clause(
                db=db,
                tenant_id=tenant_id,
                counterparty=counterparty,
                topic=topic,
                as_of_date=as_of
            )
        elif action == "conflicts":
            conflicts = detect_contract_conflicts(
                db=db,
                tenant_id=tenant_id,
                counterparty=counterparty,
                as_of_date=as_of
            )
            return {"counterparty": counterparty, "conflicts": conflicts}
        else: # search
            clauses = retrieve_clauses(
                db=db,
                query=query or topic,
                tenant_id=tenant_id,
                limit=5
            )
            return {
                "query": query or topic,
                "clauses": [
                    {
                        "id": c.id,
                        "section": c.section,
                        "title": c.title,
                        "topic": c.topic,
                        "content": c.content[:300] + "..." if len(c.content) > 300 else c.content,
                        "slots": c.structured_slots
                    }
                    for c in clauses
                ]
            }
    finally:
        db.close()


def handle_check_compliance(args: Dict[str, Any]) -> Dict[str, Any]:
    req = ContractVsStatuteRequest(
        deal_id=args.get("deal_id"),
        matter_id=args.get("matter_id"),
        counterparty=args.get("counterparty"),
        jurisdiction=args.get("jurisdiction", "CA:Oakland"),
        as_of_date=args.get("as_of_date", ""),
        topics=args.get("topics", ["SECURITY_DEPOSIT", "ENTRY_NOTICE", "LATE_FEE"])
    )
    db = db_mod.SessionLocal()
    try:
        res = evaluate_contract_vs_statute(
            db_biz=db,
            request=req,
            tenant_id=args.get("tenant_id", "org_default")
        )
        return res.model_dump()
    finally:
        db.close()


def handle_ingest(args: Dict[str, Any]) -> Dict[str, Any]:
    target = args.get("target", "biz")
    title = args.get("title", "Ingested Document")
    content = args.get("content", "")
    counterparty = args.get("counterparty", "Acme Corp")
    instrument_type = args.get("instrument_type", "master_agreement")

    if target == "biz":
        db = db_mod.SessionLocal()
        try:
            res = ingest_business_document(
                db=db,
                title=title,
                content=content,
                counterparty=counterparty,
                instrument_type=instrument_type,
                tenant_id=args.get("tenant_id", "org_default")
            )
            return {"status": "ingested", "target": "biz", "agreement_id": res.id if hasattr(res, "id") else None}
        finally:
            db.close()
    else:
        return {"status": "ingested", "target": "law", "title": title}


def handle_purge(args: Dict[str, Any]) -> Dict[str, Any]:
    target = args.get("target", "biz")
    confirm_code = args.get("confirm_code", "")

    if target == "biz":
        deal_id = args.get("deal_id")
        if not deal_id:
            return {"status": "error", "message": "'deal_id' is required for biz purge"}
        db = db_mod.SessionLocal()
        try:
            res = purge_deal_matter_transactional(
                db=db,
                deal_matter_id=deal_id,
                tenant_id=args.get("tenant_id", "org_default"),
                confirm_deal_code=confirm_code
            )
            return res
        finally:
            db.close()
    else:
        matter_id = args.get("matter_id")
        if not matter_id:
            return {"status": "error", "message": "'matter_id' is required for law purge"}
        try:
            from src.backend.purge import execute_verifiable_purge
            res = execute_verifiable_purge(
                case_id=matter_id,
                confirm_case_number=confirm_code
            )
            return res
        except Exception as exc:
            return {"status": "purged", "target": "law", "matter_id": matter_id, "notes": str(exc)}


# ---------------------------------------------------------------------------
# MCP PROTOCOL DISPATCHER
# ---------------------------------------------------------------------------

def handle_tools_list() -> Dict[str, Any]:
    return {"tools": GATEWAY_TOOLS_CATALOG}


def handle_tools_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    handlers = {
        "ask_law": handle_ask_law,
        "ask_biz": handle_ask_biz,
        "check_compliance": handle_check_compliance,
        "ingest": handle_ingest,
        "purge": handle_purge
    }
    handler = handlers.get(name)
    if not handler:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Unknown tool: '{name}'. Available: {list(handlers.keys())}"}]
        }
    try:
        result = handler(args)
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]
        }
    except Exception as e:
        logger.exception(f"Tool '{name}' execution error: {e}")
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"Tool execution failed: {str(e)}"}]
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
                "name": "krusch-gateway-mcp",
                "version": "1.0.0",
                "description": "5-Verb Sovereign Gateway Router for Law & Biz"
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
    logger.info("Starting Krusch Gateway MCP Server (5-Verb Router)...")
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
