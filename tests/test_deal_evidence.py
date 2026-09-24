import io
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

import src.backend.db
import src.backend.ingest
import src.backend.main
import src.backend.rag
from src.backend.db import DealEvidence, DealMatter, init_db
from src.backend.main import app, get_db


class TestDealEvidenceAPI(unittest.TestCase):
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
        src.backend.db.SessionLocal = cls.TestingSessionLocal

        mock_vec = [0.05] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))

        cls.client = TestClient(app)

        # Create a test deal
        db = cls.TestingSessionLocal()
        deal = DealMatter(
            id=10,
            tenant_id="org_default",
            deal_code="DEAL-TEST-010",
            company_name="Acme Corp",
            counterparty_name="CloudScale AI",
            deal_type="Vendor Procurement",
            title="Cloud Hosting Procurement Deal",
            context_facts="Evaluating vendor cloud proposal with Net 30 terms.",
            status="active"
        )
        db.add(deal)
        db.commit()
        db.close()

    def test_01_ingest_document_with_deal_evidence(self):
        doc_content = (
            "# Proposal Exhibit A: Pricing and Payment Terms\n\n"
            "Section 4.1 Payment Terms: Invoices shall be paid within thirty (30) days of receipt ('Net 30'). "
            "Late payments accrue 1.5% interest per month.\n\n"
            "# Exhibit B: System Availability Commitment\n\n"
            "Section 5.1 Service Level: Monthly Uptime Percentage commitment is 99.95% availability.\n"
        )
        file_bytes = io.BytesIO(doc_content.encode("utf-8"))
        files = {"file": ("vendor_proposal.md", file_bytes, "text/markdown")}
        data = {
            "deal_id": "10",
            "doc_type": "contract",
            "organization": "CloudScale AI"
        }

        resp = self.client.post("/api/ingest/upload", files=files, data=data, headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["deal_id"], 10)
        self.assertTrue(body["records_inserted"] >= 2)

    def test_02_get_deal_evidence_all(self):
        resp = self.client.get("/api/deals/10/evidence", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()
        self.assertTrue(len(evidence) >= 2)

        for ev in evidence:
            self.assertEqual(ev["deal_id"], 10)
            self.assertIn("tags", ev)
            self.assertIsInstance(ev["tags"], list)
            self.assertIn("summary", ev)
            self.assertIn("topic", ev)
            self.assertIsNotNone(ev["summary"])

    def test_03_get_deal_evidence_tags_summary(self):
        resp = self.client.get("/api/deals/10/evidence/tags", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["deal_id"], 10)
        self.assertTrue(len(data["tags"]) > 0)
        self.assertTrue(len(data["topics"]) > 0)
        self.assertIn("PAYMENT_TERMS", data["topics"])

    def test_04_filter_evidence_by_tag(self):
        resp = self.client.get("/api/deals/10/evidence?tag=net-30", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()
        self.assertTrue(len(evidence) >= 1)
        for ev in evidence:
            self.assertTrue(any("net-30" in t for t in ev["tags"]))

    def test_05_filter_evidence_by_topic(self):
        resp = self.client.get("/api/deals/10/evidence?topic=PAYMENT_TERMS", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()
        self.assertTrue(len(evidence) >= 1)
        for ev in evidence:
            self.assertEqual(ev["topic"], "PAYMENT_TERMS")

    def test_06_query_evidence_semantic_scoring(self):
        resp = self.client.get("/api/deals/10/evidence?q=monthly+uptime+commitment", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 200)
        evidence = resp.json()
        self.assertTrue(len(evidence) >= 1)
        first = evidence[0]
        self.assertEqual(first["topic"], "SLA_PERFORMANCE")

    def test_07_deal_not_found(self):
        resp = self.client.get("/api/deals/9999/evidence", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp.status_code, 404)

        resp_tags = self.client.get("/api/deals/9999/evidence/tags", headers={"X-Tenant-ID": "org_default"})
        self.assertEqual(resp_tags.status_code, 404)

    def test_08_tenant_isolation(self):
        # Querying deal 10 under a different tenant must return 404
        resp = self.client.get("/api/deals/10/evidence", headers={"X-Tenant-ID": "other_tenant"})
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
