"""
tests/test_compliance_join.py
=============================
Rigid unit tests for the Contract-vs-Statute Join Engine:
  - AB 12 security deposit violation (2.0 months demanded post July 1, 2024 -> VOID)
  - Pre-AB 12 compliance (2.0 months demanded in May 2024 -> ENFORCEABLE)
  - Sub-statutory entry notice (12 hrs vs 24 hr floor -> VOID)
  - More generous entry notice (48 hrs vs 24 hr floor -> ENFORCEABLE)
  - Mandatory as_of_date enforcement (HTTP 422 on missing/silent date)
  - Coverage gap identification
"""

import os
import sys
import unittest
from datetime import datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
import src.backend.main as main_mod
from src.backend.compliance import evaluate_contract_vs_statute, ContractVsStatuteRequest
from src.backend.db import (
    Agreement,
    AgreementRelation,
    Clause,
    ResolutionTraceRecord,
    init_db,
)
from src.backend.main import app, get_db


class TestComplianceJoin(unittest.TestCase):

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
        main_mod.SessionLocal = cls.Session
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
        self.db = self.Session()
        self.db.query(ResolutionTraceRecord).delete()
        self.db.query(AgreementRelation).delete()
        self.db.query(Clause).delete()
        self.db.query(Agreement).delete()
        self.db.commit()

        # Seed baseline lease agreement
        self.lease = Agreement(
            tenant_id="org_default",
            title="Bayview Master Commercial & Residential Lease",
            instrument_type="lease",
            counterparty="Pacific Crest Properties LLC",
            effective_date=datetime(2023, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(self.lease)
        self.db.flush()

        self.cl_deposit = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 4.1",
            title="Security Deposit",
            topic="SECURITY_DEPOSIT",
            authority_class="governing_agreement",
            content="Tenant shall deposit an amount equal to two (2) months' rent ($6,000) as security.",
            structured_slots={"deposit_cap_months": 2.0},
            is_active=True
        )
        self.cl_entry = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 9.2",
            title="Landlord Right of Entry",
            topic="ENTRY_NOTICE",
            authority_class="governing_agreement",
            content="Landlord may enter premises upon providing twelve (12) hours advance notice.",
            structured_slots={"entry_notice_hours": 12.0},
            is_active=True
        )
        self.db.add_all([self.cl_deposit, self.cl_entry])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_security_deposit_ab12_violation(self):
        """
        Post-AB 12 test: As of 2024-08-15, California law caps deposits at 1.0 month.
        Contract demanding 2.0 months must be flagged as VOID_AS_AGAINST_PUBLIC_POLICY.
        """
        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["SECURITY_DEPOSIT"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        self.assertEqual(len(data["findings"]), 1)
        f = data["findings"][0]
        self.assertEqual(f["topic"], "SECURITY_DEPOSIT")
        self.assertEqual(f["alignment"], "contract_less_than_mandatory")
        self.assertEqual(f["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")
        self.assertEqual(f["contract_clause"]["normalized_slot"]["deposit_cap_months"], 2.0)
        self.assertEqual(f["controlling_statute"]["normalized_slot"]["deposit_cap_months"], 1.0)
        self.assertIn("1950.5", f["controlling_statute"]["citation"])

    def test_02_security_deposit_pre_ab12_compliant(self):
        """
        Pre-AB 12 test: As of 2024-05-01, 2.0 months deposit was legal under prior law.
        Contract demanding 2.0 months is ALIGNED and ENFORCEABLE.
        """
        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-05-01",
            "topics": ["SECURITY_DEPOSIT"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "COMPLIANT")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "aligned")
        self.assertEqual(f["enforceability"], "ENFORCEABLE")
        self.assertEqual(f["controlling_statute"]["normalized_slot"]["deposit_cap_months"], 2.0)

    def test_03_entry_notice_sub_statutory_floor(self):
        """
        Cal. Civ. Code § 1954 sets 24-hr written notice floor.
        Contract clause granting only 12 hours notice is sub-statutory -> VOID.
        """
        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["ENTRY_NOTICE"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "contract_less_than_mandatory")
        self.assertEqual(f["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")
        self.assertEqual(f["contract_clause"]["normalized_slot"]["entry_notice_hours"], 12.0)
        self.assertEqual(f["controlling_statute"]["normalized_slot"]["entry_notice_hours"], 24.0)

    def test_04_entry_notice_more_generous(self):
        """
        If contract grants 48 hours notice, it exceeds statutory 24-hr floor -> contract_more_generous.
        """
        self.cl_entry.structured_slots = {"entry_notice_hours": 48.0}
        self.cl_entry.content = "Landlord shall provide at least forty-eight (48) hours notice prior to entry."
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["ENTRY_NOTICE"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "COMPLIANT")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "contract_more_generous")
        self.assertEqual(f["enforceability"], "ENFORCEABLE")

    def test_05_missing_as_of_date_rejected_http_422(self):
        """
        Invariant #2 (NO SILENT TODAY): Missing or empty as_of_date must return HTTP 422.
        """
        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "topics": ["SECURITY_DEPOSIT"]
            # as_of_date omitted
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_06_coverage_gap_untracked_topic(self):
        """
        Untracked topic yields coverage_gap and COVERAGE_GAPS_IDENTIFIED verdict.
        """
        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["UNTRACKED_TOPIC_XYZ"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "COVERAGE_GAPS_IDENTIFIED")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "coverage_gap")


if __name__ == "__main__":
    unittest.main()
