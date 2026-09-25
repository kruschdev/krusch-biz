"""
tests/test_tenant_isolation.py
==============================
Production Multi-Tenant Isolation & Zero Cross-Account Leakage Verification:
Ensures that two populated deal rooms with distinct API keys cannot cross-leak:
  - Deal Matters
  - Agreements & Metadata
  - Clauses & Structured Slots
  - Relations (AMENDS, SUPERSEDES, SCHEDULE_OF)
  - Precedence Graph Traversal Results
  - Resolution Trace Records (Audits)
  - IDOR (Insecure Direct Object Reference) Protection on Mutating Endpoints
"""

from datetime import datetime, timezone
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
import src.backend.ingest
import src.backend.main as main_mod
import src.backend.rag
from src.backend.db import Agreement, AgreementRelation, Clause, DealMatter, ResolutionTraceRecord, init_db
from src.backend.main import app, get_db


class TestTenantIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        db_mod.SessionLocal = cls.TestingSessionLocal
        cls.client = TestClient(app)

        # Mock embeddings
        mock_vec = [0.01] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        main_mod.get_embedding = MagicMock(return_value=mock_vec)

        # Configure API key requirement
        cls.secret = "master_secret_key_456"
        main_mod.settings.API_KEY = cls.secret

        # Tenant Credentials
        cls.alpha_tenant = "tenant_alpha"
        cls.alpha_key = f"{cls.alpha_tenant}:{cls.secret}"
        cls.alpha_headers = {
            "X-Tenant-ID": cls.alpha_tenant,
            "X-API-Key": cls.alpha_key
        }

        cls.beta_tenant = "tenant_beta"
        cls.beta_key = f"{cls.beta_tenant}:{cls.secret}"
        cls.beta_headers = {
            "X-Tenant-ID": cls.beta_tenant,
            "X-API-Key": cls.beta_key
        }

        # Seed Alpha Tenant Data
        db = cls.TestingSessionLocal()
        cls.alpha_deal = DealMatter(
            tenant_id=cls.alpha_tenant,
            deal_code="ALPHA-101",
            company_name="Alpha Holdings",
            counterparty_name="AlphaCounterparty",
            deal_type="M&A",
            title="Alpha Confidential Acquisition",
            context_facts="Alpha is acquiring Target A for $10M Net 30."
        )
        cls.alpha_ag = Agreement(
            tenant_id=cls.alpha_tenant,
            title="Alpha Master Agreement 2024",
            counterparty="AlphaCounterparty",
            execution_status="executed",
            instrument_type="master_agreement",
            effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            status="active"
        )
        cls.alpha_ag_2 = Agreement(
            tenant_id=cls.alpha_tenant,
            title="Alpha Amendment No. 1",
            counterparty="AlphaCounterparty",
            execution_status="executed",
            instrument_type="amendment",
            effective_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            status="active"
        )
        db.add_all([cls.alpha_deal, cls.alpha_ag, cls.alpha_ag_2])
        db.flush()

        cls.alpha_clause = Clause(
            tenant_id=cls.alpha_tenant,
            agreement_id=cls.alpha_ag.id,
            section="Section 4.1",
            title="Alpha Payment Terms",
            topic="PAYMENT_TERMS",
            content="Alpha shall pay invoices Net 30 days strictly.",
            structured_slots=json.dumps({"payment_net_days": 30})
        )
        cls.alpha_rel = AgreementRelation(
            tenant_id=cls.alpha_tenant,
            source_agreement_id=cls.alpha_ag_2.id,
            target_agreement_id=cls.alpha_ag.id,
            relation_type="AMENDS",
            clause_scope="Section 4.1",
            status="confirmed",
            reviewer_id="alpha_reviewer",
            reviewed_at=datetime.now(timezone.utc),
            notes=json.dumps({"notes": "Alpha test edge"})
        )
        db.add_all([cls.alpha_clause, cls.alpha_rel])

        # Seed Beta Tenant Data
        cls.beta_deal = DealMatter(
            tenant_id=cls.beta_tenant,
            deal_code="BETA-909",
            company_name="Beta Global",
            counterparty_name="BetaCounterparty",
            deal_type="Vendor Licensing",
            title="Beta Secret Cloud Procurement",
            context_facts="Beta is licensing Cloud Service B for $500k Net 90."
        )
        cls.beta_ag_1 = Agreement(
            tenant_id=cls.beta_tenant,
            title="Beta Master Agreement 2024",
            counterparty="BetaCounterparty",
            execution_status="executed",
            instrument_type="master_agreement",
            effective_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            status="active"
        )
        cls.beta_ag_2 = Agreement(
            tenant_id=cls.beta_tenant,
            title="Beta Amendment No. 1",
            counterparty="BetaCounterparty",
            execution_status="executed",
            instrument_type="amendment",
            effective_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
            status="active"
        )
        db.add_all([cls.beta_deal, cls.beta_ag_1, cls.beta_ag_2])
        db.flush()

        cls.beta_clause_1 = Clause(
            tenant_id=cls.beta_tenant,
            agreement_id=cls.beta_ag_1.id,
            section="Section 4.1",
            title="Beta Base Payment Terms",
            topic="PAYMENT_TERMS",
            content="Beta shall pay invoices Net 30 days initially.",
            structured_slots=json.dumps({"payment_net_days": 30})
        )
        cls.beta_clause = Clause(
            tenant_id=cls.beta_tenant,
            agreement_id=cls.beta_ag_2.id,
            section="Section 9.9",
            title="Beta Amending Payment Terms",
            topic="PAYMENT_TERMS",
            content="Beta shall pay invoices Net 90 days exclusively.",
            structured_slots=json.dumps({"payment_net_days": 90})
        )
        cls.beta_rel = AgreementRelation(
            tenant_id=cls.beta_tenant,
            source_agreement_id=cls.beta_ag_2.id,
            target_agreement_id=cls.beta_ag_1.id,
            relation_type="AMENDS",
            clause_scope="ALL",
            status="confirmed",
            notes=json.dumps({"notes": "Beta confidential relation edge"})
        )
        db.add_all([cls.beta_clause_1, cls.beta_clause, cls.beta_rel])
        db.commit()

        cls.alpha_deal_id = cls.alpha_deal.id
        cls.alpha_rel_id = cls.alpha_rel.id
        cls.beta_deal_id = cls.beta_deal.id
        cls.beta_rel_id = cls.beta_rel.id
        db.close()

    def test_01_tenant_header_spoofing_rejected(self):
        """Verify that an API key bound to tenant_alpha cannot access tenant_beta."""
        hostile_headers = {
            "X-Tenant-ID": self.beta_tenant,
            "X-API-Key": self.alpha_key  # Hostile: Alpha key attempting to act as Beta
        }
        res = self.client.get("/api/deals", headers=hostile_headers)
        self.assertEqual(res.status_code, 403)
        self.assertIn("Tenant header spoofing rejected", res.text)

    def test_02_deals_strict_isolation(self):
        """Verify that deal matters never leak across tenants."""
        # Alpha view
        res_a = self.client.get("/api/deals", headers=self.alpha_headers)
        self.assertEqual(res_a.status_code, 200)
        deals_a = res_a.json()
        self.assertTrue(any(d["deal_code"] == "ALPHA-101" for d in deals_a))
        self.assertFalse(any(d["deal_code"] == "BETA-909" for d in deals_a))

        # Beta view
        res_b = self.client.get("/api/deals", headers=self.beta_headers)
        self.assertEqual(res_b.status_code, 200)
        deals_b = res_b.json()
        self.assertTrue(any(d["deal_code"] == "BETA-909" for d in deals_b))
        self.assertFalse(any(d["deal_code"] == "ALPHA-101" for d in deals_b))

    def test_03_agreements_strict_isolation(self):
        """Verify that agreements never leak across tenants."""
        res_a = self.client.get("/api/agreements", headers=self.alpha_headers)
        self.assertEqual(res_a.status_code, 200)
        ags_a = res_a.json()
        self.assertTrue(any(a["title"] == "Alpha Master Agreement 2024" for a in ags_a))
        self.assertFalse(any(a["title"] == "Beta Master Agreement 2024" for a in ags_a))

        res_b = self.client.get("/api/agreements", headers=self.beta_headers)
        self.assertEqual(res_b.status_code, 200)
        ags_b = res_b.json()
        self.assertTrue(any(a["title"] == "Beta Master Agreement 2024" for a in ags_b))
        self.assertFalse(any(a["title"] == "Alpha Master Agreement 2024" for a in ags_b))

    def test_04_clauses_search_isolation(self):
        """Verify that clause retrieval never leaks across tenants."""
        # Alpha searches for clauses
        res_a = self.client.get("/api/clauses", headers=self.alpha_headers)
        self.assertEqual(res_a.status_code, 200)
        clauses_a = res_a.json()
        self.assertTrue(all("Alpha" in c.get("title", "") or "Net 30" in c.get("content", "") for c in clauses_a))
        self.assertFalse(any("Beta" in c.get("title", "") or "Net 90" in c.get("content", "") for c in clauses_a))

        # Beta searches for clauses
        res_b = self.client.get("/api/clauses", headers=self.beta_headers)
        self.assertEqual(res_b.status_code, 200)
        clauses_b = res_b.json()
        self.assertTrue(all("Beta" in c.get("title", "") or "Net 90" in c.get("content", "") for c in clauses_b))
        self.assertFalse(any("Alpha" in c.get("title", "") or "Net 30" in c.get("content", "") for c in clauses_b))

    def test_05_relations_isolation(self):
        """Verify that precedence relation edges never leak across tenants."""
        res_a = self.client.get("/api/relations", headers=self.alpha_headers)
        self.assertEqual(res_a.status_code, 200)
        rels_a = res_a.json()
        self.assertTrue(any(r["id"] == self.alpha_rel_id for r in rels_a))
        self.assertFalse(any(r["id"] == self.beta_rel_id for r in rels_a))

        res_b = self.client.get("/api/relations", headers=self.beta_headers)
        self.assertEqual(res_b.status_code, 200)
        rels_b = res_b.json()
        self.assertTrue(any(r["id"] == self.beta_rel_id for r in rels_b))
        self.assertFalse(any(r["id"] == self.alpha_rel_id for r in rels_b))

    def test_06_precedence_graph_traversal_isolation(self):
        """Verify that DAG walker strictly partitions graph traversal by tenant_id."""
        # Alpha attempts to resolve Beta's counterparty
        res_a = self.client.get(
            "/api/resolver/controlling-clause",
            params={"counterparty": "BetaCounterparty", "topic": "PAYMENT_TERMS"},
            headers=self.alpha_headers
        )
        self.assertEqual(res_a.status_code, 200)
        data_a = res_a.json()
        self.assertIsNone(data_a.get("controlling_clause"))
        self.assertEqual(data_a.get("status"), "not_found")

        # Beta successfully resolves Beta's counterparty
        res_b = self.client.get(
            "/api/resolver/controlling-clause",
            params={"counterparty": "BetaCounterparty", "topic": "PAYMENT_TERMS"},
            headers=self.beta_headers
        )
        self.assertEqual(res_b.status_code, 200)
        data_b = res_b.json()
        self.assertIsNotNone(data_b.get("controlling_clause"))
        self.assertIn("Net 90", data_b["controlling_clause"].get("content", ""))

    def test_07_idor_protection_on_mutating_endpoints(self):
        """Verify that attempting to mutate or delete another tenant's object by ID fails with 404."""
        # Alpha tries to delete Beta's deal
        del_deal_res = self.client.delete(f"/api/deals/{self.beta_deal_id}/hard-delete", headers=self.alpha_headers)
        self.assertEqual(del_deal_res.status_code, 404)

        # Alpha tries to delete Beta's relation
        del_rel_res = self.client.delete(f"/api/relations/{self.beta_rel_id}", headers=self.alpha_headers)
        self.assertEqual(del_rel_res.status_code, 404)

        # Alpha tries to edit Beta's relation
        patch_rel_res = self.client.patch(
            f"/api/relations/{self.beta_rel_id}",
            json={"clause_scope": "HACKED"},
            headers=self.alpha_headers
        )
        self.assertEqual(patch_rel_res.status_code, 404)

    def test_08_resolution_traces_isolation(self):
        """Verify that immutable precedence audit traces never leak across tenants."""
        # 1. Beta runs a resolution which logs a trace
        res_b = self.client.get(
            "/api/resolver/controlling-clause",
            params={"counterparty": "BetaCounterparty", "topic": "PAYMENT_TERMS"},
            headers=self.beta_headers
        )
        self.assertEqual(res_b.status_code, 200)

        # 2. Beta inspects traces -> sees Beta trace
        traces_b_res = self.client.get("/api/resolution-traces", headers=self.beta_headers)
        self.assertEqual(traces_b_res.status_code, 200)
        traces_b = traces_b_res.json()
        self.assertTrue(len(traces_b) > 0)
        self.assertTrue(all(t["tenant_id"] == self.beta_tenant for t in traces_b))
        self.assertTrue(any(t["counterparty"] == "BetaCounterparty" for t in traces_b))

        # 3. Alpha inspects traces -> strictly 0 traces from Beta
        traces_a_res = self.client.get("/api/resolution-traces", headers=self.alpha_headers)
        self.assertEqual(traces_a_res.status_code, 200)
        traces_a = traces_a_res.json()
        self.assertTrue(all(t["tenant_id"] == self.alpha_tenant for t in traces_a))
        self.assertFalse(any(t["tenant_id"] == self.beta_tenant for t in traces_a))

        # Assert zero intersection between Alpha and Beta trace IDs
        beta_trace_ids = {t["id"] for t in traces_b}
        alpha_trace_ids = {t["id"] for t in traces_a}
        self.assertEqual(len(beta_trace_ids.intersection(alpha_trace_ids)), 0)
        # Beta's successful resolution trace is never visible to Alpha
        self.assertFalse(any(t["id"] in beta_trace_ids for t in traces_a))
        self.assertFalse(any(t["status"] == "resolved" for t in traces_a))


if __name__ == "__main__":
    unittest.main()

