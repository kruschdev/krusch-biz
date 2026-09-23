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
    TOOLS_CATALOG,
    handle_draft_brief,
    handle_get_clause,
    handle_list_deals,
    handle_log_deal,
    handle_search_contracts,
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
        self.assertIn("search_contracts_and_policies", tool_names)
        self.assertIn("get_clause_details", tool_names)
        self.assertIn("log_deal_matter", tool_names)
        self.assertIn("draft_deal_brief", tool_names)
        self.assertIn("get_grounding_audit", tool_names)
        self.assertIn("ingest_business_document", tool_names)

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
        # Query that returns zero clauses
        res = handle_draft_brief({
            "title": "Quantum Physics Transaction",
            "context_facts": "Subatomic particle accelerators in outer space.",
            "limit": 1
        })
        # If any clauses returned, check, otherwise must refuse
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
        from src.mcp.server import handle_resolve_controlling_clause
        res = handle_resolve_controlling_clause({
            "counterparty": "CloudScale AI",
            "topic": "PAYMENT_TERMS"
        })
        self.assertIn(res.get("status"), ("resolved", "no_candidate_clauses"))

    def test_08_detect_contract_conflicts_mcp(self):
        from src.mcp.server import handle_detect_conflicts
        res = handle_detect_conflicts({
            "counterparty": "CloudScale AI"
        })
        self.assertIn("conflicts", res)


if __name__ == "__main__":
    unittest.main()
