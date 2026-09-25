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

    def test_07_deposit_return_extended_timeline_void(self):
        """
        Cal. Civ. Code § 1950.5(g)(1) sets 21 calendar day ceiling for deposit returns.
        A lease clause allowing 45 days is VOID_AS_AGAINST_PUBLIC_POLICY.
        """
        cl_return = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 4.3",
            title="Return of Security Deposit",
            topic="DEPOSIT_RETURN",
            authority_class="governing_agreement",
            content="Landlord shall return any unused deposit funds within forty-five (45) days of surrender.",
            structured_slots={"deposit_return_days": 45.0},
            is_active=True
        )
        self.db.add(cl_return)
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["DEPOSIT_RETURN"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        f = data["findings"][0]
        self.assertEqual(f["topic"], "DEPOSIT_RETURN")
        self.assertEqual(f["alignment"], "contract_less_than_mandatory")
        self.assertEqual(f["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")
        self.assertIn("1950.5", f["controlling_statute"]["citation"])

    def test_08_deposit_return_expedited_timeline_more_generous(self):
        """
        A lease granting 14 days deposit return exceeds statutory protection (21 days) -> contract_more_generous.
        """
        cl_return = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 4.3",
            title="Expedited Deposit Return",
            topic="DEPOSIT_RETURN",
            authority_class="governing_agreement",
            content="Landlord guarantees deposit accounting and refund within fourteen (14) calendar days.",
            structured_slots={"deposit_return_days": 14.0},
            is_active=True
        )
        self.db.add(cl_return)
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["DEPOSIT_RETURN"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "COMPLIANT")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "contract_more_generous")
        self.assertEqual(f["enforceability"], "ENFORCEABLE")

    def test_09_habitability_repair_deduct_waiver_void(self):
        """
        Cal. Civ. Code § 1942.1 renders any agreement waiving rights under § 1941 or § 1942 void.
        A clause waiving repair-and-deduct rights is VOID_AS_AGAINST_PUBLIC_POLICY.
        """
        cl_hab = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 11.4",
            title="Waiver of Habitability Remedies",
            topic="HABITABILITY_WAIVER",
            authority_class="governing_agreement",
            content="Tenant accepts premises strictly as-is and expressly waives all rights under Civil Code Section 1942 to repair and deduct.",
            structured_slots={"waives_habitability": True, "waives_repair_deduct": True},
            is_active=True
        )
        self.db.add(cl_hab)
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["HABITABILITY_WAIVER"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "contract_less_than_mandatory")
        self.assertEqual(f["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")
        self.assertIn("1942.1", f["controlling_statute"]["citation"])

    def test_10_commercial_lease_deposit_flexibility(self):
        """
        Under Cal. Civ. Code § 1950.7, commercial tenancies are not subject to AB 12 1-month cap.
        Commercial lease demanding 3.0 months deposit is ALIGNED and ENFORCEABLE.
        """
        comm_lease = Agreement(
            tenant_id="org_default",
            title="Commercial Warehouse Lease",
            instrument_type="commercial_lease",
            counterparty="Pacific Crest Commercial Holdings LLC",
            effective_date=datetime(2024, 8, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(comm_lease)
        self.db.flush()

        cl_comm_dep = Clause(
            tenant_id="org_default",
            agreement_id=comm_lease.id,
            section="Section 3.1",
            title="Commercial Deposit",
            topic="COMMERCIAL_SECURITY_DEPOSIT",
            authority_class="governing_agreement",
            content="Tenant shall deposit an amount equal to three (3) months' base rent ($15,000) as security.",
            structured_slots={"deposit_cap_months": 3.0},
            is_active=True
        )
        self.db.add(cl_comm_dep)
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Commercial Holdings LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["COMMERCIAL_SECURITY_DEPOSIT"],
            "property_type": "commercial"
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "COMPLIANT")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "aligned")
        self.assertEqual(f["enforceability"], "ENFORCEABLE")
        self.assertIn("1950.7", f["controlling_statute"]["citation"])

    def test_11_retaliation_defense_waiver_void(self):
        """
        Cal. Civ. Code § 1942.5(h) renders any tenant waiver of retaliation protections void.
        """
        cl_ret = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 18.2",
            title="Waiver of Retaliation Defenses",
            topic="RETALIATION_WAIVER",
            authority_class="governing_agreement",
            content="Tenant covenants not to raise any defense of retaliation under Civil Code Section 1942.5.",
            structured_slots={"waives_retaliation_defense": True},
            is_active=True
        )
        self.db.add(cl_ret)
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["RETALIATION_WAIVER"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "contract_less_than_mandatory")
        self.assertEqual(f["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")
        self.assertIn("1942.5", f["controlling_statute"]["citation"])

    def test_12_excessive_late_fee_liquidated_damages_void(self):
        """
        Cal. Civ. Code § 1671(d) caps late fees to reasonable approximations of damages (typically 5%).
        A 15% late fee clause is non-compliant and VOID_AS_AGAINST_PUBLIC_POLICY.
        """
        cl_late = Clause(
            tenant_id="org_default",
            agreement_id=self.lease.id,
            section="Section 5.2",
            title="Late Charge",
            topic="LATE_FEE",
            authority_class="governing_agreement",
            content="A late fee equal to fifteen percent (15%) of delinquent rent shall apply after 3 days.",
            structured_slots={"late_penalty_pct": 15.0},
            is_active=True
        )
        self.db.add(cl_late)
        self.db.commit()

        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "CA:Oakland",
            "as_of_date": "2024-08-15",
            "topics": ["LATE_FEE"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "NON_COMPLIANT_TERMS_FOUND")
        f = data["findings"][0]
        self.assertEqual(f["alignment"], "contract_less_than_mandatory")
        self.assertEqual(f["enforceability"], "VOID_AS_AGAINST_PUBLIC_POLICY")

    def test_13_unsupported_jurisdiction_returns_unsupported(self):
        """Verify that an unknown or non-CA jurisdiction returns UNSUPPORTED_JURISDICTION."""
        payload = {
            "counterparty": "Pacific Crest Properties LLC",
            "jurisdiction": "NY:NewYork",
            "as_of_date": "2024-08-15",
            "topics": ["SECURITY_DEPOSIT"]
        }
        resp = self.client.post("/conflicts/contract-vs-statute", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["verdict"], "UNSUPPORTED_JURISDICTION")
        self.assertEqual(data["coverage_completeness"], "none")
        self.assertEqual(len(data["findings"]), 1)
        self.assertIn("UNSUPPORTED_JURISDICTION", data["findings"][0]["explanation"])
        self.assertIn("ca_demo.yaml", data["findings"][0]["explanation"])


if __name__ == "__main__":
    unittest.main()
