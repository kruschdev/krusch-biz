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

import src.backend.ingest
import src.backend.main
import src.backend.rag
from src.backend.db import Agreement, Clause, init_db
from src.backend.ingest import ingest_mock_data
from src.backend.main import app, get_db


class TestAPI(unittest.TestCase):
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
        cls.client = TestClient(app)

        mock_vec = [0.01] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.main.get_embedding = MagicMock(return_value=mock_vec)

        db = cls.TestingSessionLocal()
        ingest_mock_data(db)
        db.close()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_01_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "kruschbiz-backend")

    def test_02_deals_crud_and_purge(self):
        # Create
        create_resp = self.client.post("/api/deals", json={
            "deal_code": "DEAL-API-001",
            "company_name": "Acme Corp",
            "counterparty_name": "CloudScale AI",
            "deal_type": "Vendor Procurement",
            "title": "Cloud Hosting Deal",
            "context_facts": "Evaluating cloud hosting terms and liability caps."
        })
        self.assertEqual(create_resp.status_code, 201)
        deal_id = create_resp.json()["id"]

        # Read
        get_resp = self.client.get(f"/api/deals/{deal_id}")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["deal_code"], "DEAL-API-001")

        # Update
        patch_resp = self.client.patch(f"/api/deals/{deal_id}", json={
            "title": "Cloud Hosting Master Deal (Updated)"
        })
        self.assertEqual(patch_resp.status_code, 200)
        self.assertIn("Updated", patch_resp.json()["title"])

        # Soft Delete
        del_resp = self.client.delete(f"/api/deals/{deal_id}")
        self.assertEqual(del_resp.status_code, 200)

        # List excludes soft deleted
        list_resp = self.client.get("/api/deals")
        self.assertEqual(list_resp.status_code, 200)
        deal_ids = [d["id"] for d in list_resp.json()]
        self.assertNotIn(deal_id, deal_ids)

        # Hard Purge
        purge_resp = self.client.delete(f"/api/deals/{deal_id}/purge")
        self.assertEqual(purge_resp.status_code, 200)
        self.assertIn("permanently purged", purge_resp.json()["message"])

    def test_03_search_clauses(self):
        resp = self.client.get("/api/clauses?q=payment+terms&limit=3")
        self.assertEqual(resp.status_code, 200)
        clauses = resp.json()
        self.assertGreaterEqual(len(clauses), 1)

    def test_04_consult_endpoint(self):
        resp = self.client.get("/api/consult?query=Vendor+payment+terms+Net+30")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("analysis", data)
        self.assertIn("grounding_stats", data)
        self.assertGreaterEqual(data["grounding_stats"]["pass_rate"], 0.0)

    def test_05_export_docx_endpoint(self):
        resp = self.client.post("/api/consult/export/docx", json={
            "deal_title": "Acme Deal",
            "deal_code": "DEAL-001",
            "brief_content": "# I. KEY COMMERCIAL TERMS\nTerms overview.\n"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content[:4], b"PK\x03\x04")

    def test_06_upload_document(self):
        content = b"# Enterprise Addendum\n\n## Section 1 Terms\nPayment Net 30.\n"
        resp = self.client.post(
            "/api/ingest/upload",
            files={"file": ("addendum.md", io.BytesIO(content), "text/markdown")},
            data={"doc_type": "contract"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["filename"], "addendum.md")

    def test_07_upload_invalid_extension(self):
        resp = self.client.post(
            "/api/ingest/upload",
            files={"file": ("binary.bin", io.BytesIO(b"data"), "application/octet-stream")},
            data={"doc_type": "contract"}
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported document format", resp.json()["detail"])

    def test_08_diff_endpoint(self):
        db = self.TestingSessionLocal()
        ag1 = Agreement(
            tenant_id="org_default",
            title="Cloud Services Master Agreement 2024",
            instrument_type="master_services_agreement",
            counterparty="VendorCorp"
        )
        ag2 = Agreement(
            tenant_id="org_default",
            title="Cloud Services Master Agreement 2026",
            instrument_type="master_services_agreement",
            counterparty="VendorCorp"
        )
        db.add(ag1)
        db.add(ag2)
        db.flush()

        cl1 = Clause(
            tenant_id="org_default",
            agreement_id=ag1.id,
            section="Section 4.1",
            title="Payment Terms",
            topic="PAYMENT_TERMS",
            authority_class="governing_agreement",
            content="Customer shall pay within thirty (30) days.",
            structured_slots={"net_days": 30}
        )
        cl2 = Clause(
            tenant_id="org_default",
            agreement_id=ag2.id,
            section="Section 4.1",
            title="Payment Terms",
            topic="PAYMENT_TERMS",
            authority_class="governing_agreement",
            content="Customer shall pay within forty-five (45) days.",
            structured_slots={"net_days": 45}
        )
        db.add(cl1)
        db.add(cl2)
        db.commit()
        ag1_id, ag2_id = ag1.id, ag2.id
        db.close()

        resp = self.client.get(f"/api/resolver/diff?agreement_a_id={ag1_id}&agreement_b_id={ag2_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "compared")
        self.assertEqual(data["slot_changes_count"], 1)
        self.assertEqual(data["slot_changes"][0]["slot"], "net_days")
        self.assertEqual(data["slot_changes"][0]["value_a"], 30)
        self.assertEqual(data["slot_changes"][0]["value_b"], 45)

    def test_09_diff_endpoint_not_found(self):
        resp = self.client.get("/api/resolver/diff?agreement_a_id=9999&agreement_b_id=9998")
        self.assertEqual(resp.status_code, 404)

    def test_10_what_controls_export_endpoint(self):
        resp = self.client.post("/api/resolver/what-controls-export", json={
            "counterparty": "VendorCorp",
            "as_of_date": "2026-06-01"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["counterparty"], "VendorCorp")
        self.assertEqual(data["as_of_date"], "2026-06-01")
        self.assertIn("markdown", data)
        self.assertIn("GENERAL COUNSEL CONTROLLING TERMS MEMORANDUM", data["markdown"])
        self.assertTrue(data["topics_evaluated"] >= 1)


if __name__ == "__main__":
    unittest.main()

