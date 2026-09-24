"""
tests/test_relation_ingest.py
=============================
Unit tests verifying relation edge extraction at ingest time and relations CRUD:
  - Extraction of proposed AMENDS relations from filename and preamble cues
  - Scope detection (Section 4.1 vs ALL)
  - Target agreement resolution against existing DB agreements
  - Source excerpt span capture
  - SOW SCHEDULE_OF relation extraction
  - Human review workflow: GET /api/relations, PATCH /confirm, DELETE
"""

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
from src.backend.db import Agreement, AgreementRelation, init_db
from src.backend.ingest import extract_proposed_relations
from src.backend.main import app, get_db


class TestRelationIngest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.Session = sessionmaker(bind=cls.engine)
        src.backend.db.engine = cls.engine
        src.backend.db.SessionLocal = cls.Session
        src.backend.ingest.SessionLocal = cls.Session

        init_db(cls.engine)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    def setUp(self):
        db = self.Session()
        db.query(AgreementRelation).delete()
        db.query(Agreement).delete()

        # Seed base MSA
        self.base_msa = Agreement(
            tenant_id="org_default",
            title="Acme Corp - Master Services Agreement",
            instrument_type="master_services_agreement",
            counterparty="CloudScale AI",
            status="active"
        )
        db.add(self.base_msa)
        db.commit()
        db.refresh(self.base_msa)
        db.close()

    def test_01_extract_proposed_amends_relation(self):
        """Verify extraction of AMENDS relation with scope and span from preamble."""
        db = self.Session()
        try:
            # Create amendment agreement record
            amend_ag = Agreement(
                tenant_id="org_default",
                title="Acme Corp - Amendment No. 1",
                instrument_type="amendment",
                counterparty="CloudScale AI",
                status="active"
            )
            db.add(amend_ag)
            db.commit()
            db.refresh(amend_ag)

            text = (
                "This Amendment No. 1 to that certain Master Services Agreement dated January 1, 2025 "
                "is entered into by and between Acme Corp and CloudScale AI. "
                "Section 4.1 of the Agreement is hereby amended to modify payment terms to Net 45."
            )
            filename = "Amendment_1_to_Acme_MSA.pdf"

            proposed = extract_proposed_relations(
                text=text,
                filename=filename,
                tenant_id="org_default",
                db=db,
                source_ag_id=amend_ag.id
            )

            self.assertGreaterEqual(len(proposed), 1)
            rel = proposed[0]
            self.assertEqual(rel["relation_type"], "AMENDS")
            self.assertEqual(rel["target_agreement_id"], self.base_msa.id)
            self.assertEqual(rel["clause_scope"], "Section 4.1")
            self.assertEqual(rel["status"], "proposed")
            self.assertGreaterEqual(rel["confidence"], 0.85)
            self.assertIn("Section 4.1", rel["source_excerpt"])
        finally:
            db.close()

    def test_02_extract_proposed_sow_relation(self):
        """Verify extraction of SCHEDULE_OF relation for a Statement of Work."""
        db = self.Session()
        try:
            sow_ag = Agreement(
                tenant_id="org_default",
                title="Acme Corp - SOW #1 Cloud Engineering",
                instrument_type="statement_of_work",
                counterparty="CloudScale AI",
                status="active"
            )
            db.add(sow_ag)
            db.commit()
            db.refresh(sow_ag)

            text = (
                "This Statement of Work #1 is entered into pursuant to that certain Master Services Agreement "
                "by and between Acme Corp and CloudScale AI. Deliverables include infrastructure architecture."
            )
            filename = "SOW_1_Cloud_Services.pdf"

            proposed = extract_proposed_relations(
                text=text,
                filename=filename,
                tenant_id="org_default",
                db=db,
                source_ag_id=sow_ag.id
            )

            self.assertGreaterEqual(len(proposed), 1)
            rel = proposed[0]
            self.assertEqual(rel["relation_type"], "SCHEDULE_OF")
            self.assertEqual(rel["target_agreement_id"], self.base_msa.id)
            self.assertEqual(rel["status"], "proposed")
        finally:
            db.close()

    def test_03_relations_api_review_and_confirm_workflow(self):
        """Verify listing relations and human confirmation via PATCH /confirm."""
        db = self.Session()
        try:
            amend_ag = Agreement(
                tenant_id="org_default",
                title="Acme Corp - Amendment #2",
                instrument_type="amendment",
                status="active"
            )
            db.add(amend_ag)
            db.commit()
            db.refresh(amend_ag)

            rel_data = {
                "source_agreement_id": amend_ag.id,
                "target_agreement_id": self.base_msa.id,
                "relation_type": "AMENDS",
                "clause_scope": "Section 10.1",
                "notes": '{"status": "proposed", "confidence": 0.95, "source_excerpt": "Amends Section 10.1"}'
            }
            create_resp = self.client.post("/api/relations", json=rel_data, headers={"X-Tenant-ID": "org_default"})
            self.assertEqual(create_resp.status_code, 201)
            rel_id = create_resp.json()["id"]

            # List relations filtered by status proposed
            list_resp = self.client.get("/api/relations?status=proposed", headers={"X-Tenant-ID": "org_default"})
            self.assertEqual(list_resp.status_code, 200)
            items = list_resp.json()
            self.assertTrue(any(i["id"] == rel_id for i in items))

            # Confirm relation
            conf_resp = self.client.patch(f"/api/relations/{rel_id}/confirm", headers={"X-Tenant-ID": "org_default"})
            self.assertEqual(conf_resp.status_code, 200)
            self.assertEqual(conf_resp.json()["status"], "confirmed")

            # Verify it shows as confirmed
            check_resp = self.client.get("/api/relations?status=confirmed", headers={"X-Tenant-ID": "org_default"})
            self.assertEqual(check_resp.status_code, 200)
            confirmed_items = check_resp.json()
            self.assertTrue(any(i["id"] == rel_id for i in confirmed_items))

            # Delete relation
            del_resp = self.client.delete(f"/api/relations/{rel_id}", headers={"X-Tenant-ID": "org_default"})
            self.assertEqual(del_resp.status_code, 200)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
