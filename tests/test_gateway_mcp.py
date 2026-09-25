"""
tests/test_gateway_mcp.py
=========================
Unit tests for the 5-verb Sovereign Gateway MCP Router:
  1. Exact 5-tool catalog validation (ask_law, ask_biz, check_compliance, ingest, purge)
  2. Strict token budget enforcement (<450 prompt tokens)
  3. JSON-RPC protocol execution: initialize, tools/list, tools/call
  4. check_compliance join execution over JSON-RPC
  5. ask_biz and ask_law dispatch verification
"""

import json
import os
import sys
import unittest
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
from src.backend.db import (
    Agreement,
    AgreementRelation,
    Clause,
    ResolutionTraceRecord,
    init_db,
)
from src.mcp.gateway import (
    GATEWAY_TOOLS_CATALOG,
    handle_tools_call,
    handle_tools_list,
    process_json_rpc,
)


class TestGatewayMCP(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.Session = sessionmaker(bind=cls.engine)
        db_mod.engine = cls.engine
        db_mod.SessionLocal = cls.Session
        init_db(cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.db.query(ResolutionTraceRecord).delete()
        self.db.query(AgreementRelation).delete()
        self.db.query(Clause).delete()
        self.db.query(Agreement).delete()
        self.db.commit()

        # Seed an agreement for ask_biz and check_compliance
        self.lease = Agreement(
            tenant_id="org_default",
            title="Standard Commercial Lease",
            instrument_type="lease",
            counterparty="Meridian Bay LLC",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(self.lease)
        self.db.flush()

        self.cl_deposit = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 3.1",
            title="Security Deposit",
            topic="SECURITY_DEPOSIT",
            authority_class="governing_agreement",
            content="Tenant shall pay two months rent as security deposit.",
            structured_slots={"deposit_cap_months": 2.0},
            is_active=True
        )
        self.db.add(self.cl_deposit)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_catalog_has_exact_5_verbs(self):
        """Gateway MCP must consolidate tool sprawl into exactly 5 canonical verbs."""
        tools = GATEWAY_TOOLS_CATALOG
        self.assertEqual(len(tools), 5)
        names = {t["name"] for t in tools}
        expected = {"ask_law", "ask_biz", "check_compliance", "ingest", "purge"}
        self.assertEqual(names, expected)

    def test_02_strict_token_budget_under_450_tokens(self):
        """
        Hard Token Budget Invariant:
        Tool schema catalog must be strictly <450 tokens (~1800 characters)
        so local 7B/14B models do not waste context window on tool schemas.
        """
        catalog_json = json.dumps(GATEWAY_TOOLS_CATALOG, separators=(',', ':'))
        # Rough token approximation: 1 token ~= 4 chars of dense JSON
        approx_tokens = len(catalog_json) / 4.0
        self.assertLess(
            approx_tokens,
            450,
            f"Gateway tools catalog ({approx_tokens:.1f} tokens, {len(catalog_json)} chars) exceeds 450-token budget!"
        )

    def test_03_json_rpc_initialize_and_tools_list(self):
        """Verify initialize and tools/list standard JSON-RPC handlers."""
        init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        init_res = json.loads(process_json_rpc(init_req))
        self.assertEqual(init_res["id"], 1)
        self.assertEqual(init_res["result"]["serverInfo"]["name"], "krusch-gateway-mcp")

        list_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        list_res = json.loads(process_json_rpc(list_req))
        self.assertEqual(list_res["id"], 2)
        self.assertEqual(len(list_res["result"]["tools"]), 5)

    def test_04_check_compliance_via_gateway_rpc(self):
        """Execute The Join (check_compliance) over JSON-RPC."""
        call_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "check_compliance",
                "arguments": {
                    "counterparty": "Meridian Bay LLC",
                    "jurisdiction": "CA:Oakland",
                    "as_of_date": "2024-08-15",
                    "topics": ["SECURITY_DEPOSIT"]
                }
            }
        })
        call_res = json.loads(process_json_rpc(call_req))
        self.assertEqual(call_res["id"], 3)
        content_text = call_res["result"]["content"][0]["text"]
        data = json.loads(content_text)
        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        self.assertEqual(data["findings"][0]["alignment"], "contract_less_than_mandatory")
        self.assertEqual(data["findings"][0]["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")

    def test_05_ask_biz_via_gateway_rpc(self):
        """Execute ask_biz controlling clause resolution over JSON-RPC."""
        call_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "ask_biz",
                "arguments": {
                    "action": "resolve",
                    "counterparty": "Meridian Bay LLC",
                    "topic": "SECURITY_DEPOSIT",
                    "as_of_date": "2024-05-01"
                }
            }
        })
        call_res = json.loads(process_json_rpc(call_req))
        self.assertEqual(call_res["id"], 4)
        content_text = call_res["result"]["content"][0]["text"]
        data = json.loads(content_text)
        self.assertEqual(data["status"], "resolved")
        self.assertEqual(data["controlling_clause"]["section"], "Section 3.1")


if __name__ == "__main__":
    unittest.main()
