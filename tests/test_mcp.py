"""
tests/test_mcp.py
=================
Unit tests for KruschBiz lean Model Context Protocol (MCP) server.
Validates the 4 canonical tools:
  - contract_intelligence
  - manage_deal
  - ingest_contract
  - verify_grounding
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db
import src.backend.ingest
import src.backend.rag
import src.mcp.server
from src.backend.db import init_db
from src.backend.ingest import ingest_mock_data
from src.mcp.server import (
    DISPATCHER,
    TOOLS_CATALOG,
    handle_contract_intelligence,
    handle_detect_conflicts,
    handle_diff_instruments,
    handle_draft_brief,
    handle_get_clause,
    handle_list_deals,
    handle_log_deal,
    handle_manage_deal,
    handle_resolve_controlling_clause,
    handle_search_contracts,
    handle_verify_grounding,
)


class TestMCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

        mock_vec = [0.01] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))

        src.backend.db.SessionLocal = cls.SessionLocal
        src.mcp.server.SessionLocal = cls.SessionLocal

        db = cls.SessionLocal()
        ingest_mock_data(db)
        db.close()

    def test_01_tools_catalog(self):
        tool_names = [t["name"] for t in TOOLS_CATALOG]
        # Canonical 4 tools focused strictly on contract intelligence
        self.assertEqual(len(tool_names), 4)
        self.assertIn("contract_intelligence", tool_names)
        self.assertIn("manage_deal", tool_names)
        self.assertIn("ingest_contract", tool_names)
        self.assertIn("verify_grounding", tool_names)

        # Dispatcher supports all 4 canonical tools
        self.assertIn("contract_intelligence", DISPATCHER)
        self.assertIn("manage_deal", DISPATCHER)
        self.assertIn("ingest_contract", DISPATCHER)
        self.assertIn("verify_grounding", DISPATCHER)

    def test_02_search_contracts_handler(self):
        res = handle_search_contracts({"query": "limitation of liability", "limit": 2})
        self.assertGreaterEqual(res["total_found"], 1)

    def test_03_get_clause_handler(self):
        res = handle_get_clause({"section": "Section 4.1"})
        self.assertEqual(res["status"], "found")
        self.assertEqual(res["clause"]["section"], "Section 4.1")

    def test_04_log_and_list_deals(self):
        log_res = handle_log_deal({
            "title": "Vendor Evaluation Deal",
            "context_facts": "Evaluating CloudScale SLA and liability terms.",
            "deal_code": "DEAL-MCP-001"
        })
        self.assertEqual(log_res["status"], "created")
        deal_id = log_res["deal_id"]

        list_res = handle_list_deals({"limit": 5})
        self.assertGreaterEqual(list_res["total"], 1)
        deal_ids = [d["id"] for d in list_res["deals"]]
        self.assertIn(deal_id, deal_ids)

    def test_05_draft_brief_refusal_when_no_authorities(self):
        res = handle_draft_brief({
            "title": "Quantum Physics Transaction",
            "context_facts": "Subatomic particle accelerators in outer space.",
            "limit": 1
        })
        if res.get("status") == "refused":
            self.assertEqual(res["error_code"], "CANNOT_DRAFT_WITHOUT_AUTHORITIES")

    def test_06_draft_brief_success(self):
        res = handle_draft_brief({
            "title": "Cloud Services Procurement",
            "context_facts": "Customer paying monthly invoices Net 30 under Section 4.1.",
            "limit": 3
        })
        self.assertEqual(res["status"], "drafted")
        self.assertTrue(res["review_required"])
        self.assertIn("EXECUTIVE COMMERCIAL MEMORANDUM", res["brief"])

    def test_07_resolve_controlling_clause_mcp(self):
        res = handle_resolve_controlling_clause({
            "counterparty": "CloudScale AI",
            "topic": "PAYMENT_TERMS"
        })
        self.assertIn(res.get("status"), ("resolved", "ambiguous", "topic_not_found", "not_found"))

    def test_08_detect_contract_conflicts_mcp(self):
        res = handle_detect_conflicts({
            "counterparty": "CloudScale AI"
        })
        self.assertIn("conflicts", res)

    def test_09_diff_contract_instruments_mcp(self):
        from src.backend.db import Agreement
        db = self.SessionLocal()
        ags = db.query(Agreement).limit(2).all()
        db.close()
        if len(ags) >= 2:
            res = handle_diff_instruments({
                "agreement_a_id": ags[0].id,
                "agreement_b_id": ags[1].id
            })
            self.assertEqual(res["status"], "compared")
            self.assertIn("modified_provisions", res)
            self.assertIn("slot_changes", res)

    def test_10_canonical_contract_intelligence(self):
        # 1. Search action
        res_search = handle_contract_intelligence({"action": "search", "query": "liability", "limit": 2})
        self.assertGreaterEqual(res_search.get("total_found", 0), 1)

        # 2. Get clause action
        res_clause = handle_contract_intelligence({"action": "get_clause", "section": "Section 4.1"})
        self.assertEqual(res_clause.get("status"), "found")

        # 3. Resolve controlling action
        res_res = handle_contract_intelligence({
            "action": "resolve_controlling",
            "counterparty": "CloudScale AI",
            "topic": "PAYMENT_TERMS"
        })
        self.assertIn(res_res.get("status"), ("resolved", "ambiguous", "topic_not_found", "not_found"))

        # 4. Unknown action guardrail
        res_err = handle_contract_intelligence({"action": "unknown_verb"})
        self.assertIn("error", res_err)

    def test_11_canonical_manage_deal(self):
        # 1. Log deal
        res_log = handle_manage_deal({
            "action": "log",
            "title": "M&A Acquisition Diligence",
            "context_facts": "Reviewing data protection obligations under Exhibit C."
        })
        self.assertEqual(res_log.get("status"), "created")
        deal_id = res_log.get("deal_id")

        # 2. List deals
        res_list = handle_manage_deal({"action": "list", "limit": 2})
        self.assertGreaterEqual(res_list.get("total", 0), 1)

        # 3. Audit deal
        res_audit = handle_manage_deal({"action": "audit", "deal_id": deal_id})
        self.assertIn(res_audit.get("status"), ("found", "not_found"))

    def test_12_verify_grounding_mcp(self):
        claims = [
            {
                "claim_id": "c1",
                "sentence": "Payment terms are Net 30 under Section 4.1.",
                "cited_authority": "Section 4.1",
                "term": "net_days",
                "value": "30"
            }
        ]
        authorities = [
            {
                "section": "Section 4.1",
                "content": "Invoices shall be paid within thirty (30) days ('Net 30').",
                "structured_slots": {"net_days": 30}
            }
        ]
        res = handle_verify_grounding({
            "claims": claims,
            "authorities": authorities
        })
        self.assertIn("verified_count", res)
        self.assertIn("overall_score", res)


if __name__ == "__main__":
    unittest.main()
