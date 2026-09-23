"""
tests/test_resolver.py
======================
Unit and integration tests for controlling-document resolver and conflict detection.
"""

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
from src.backend.db import Agreement, AgreementRelation, Clause, init_db
from src.backend.resolver import detect_contract_conflicts, resolve_controlling_clause


class TestControllingDocumentResolver(unittest.TestCase):

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
        # Clean state
        self.db.query(AgreementRelation).delete()
        self.db.query(Clause).delete()
        self.db.query(Agreement).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_resolve_amendment_over_governing_agreement(self):
        """Verify that an amendment controlling clause outranks base governing agreement."""
        # Base Agreement (Net 30)
        msa = Agreement(
            tenant_id="tenant_test",
            title="Acme Corp - Master Agreement",
            instrument_type="master_services_agreement",
            counterparty="VendorCorp",
            effective_date=datetime(2023, 1, 1),
            status="active"
        )
        self.db.add(msa)
        self.db.flush()

        cl_msa = Clause(
            tenant_id="tenant_test",
            agreement_id=msa.id,
            section="Section 4.1",
            title="Payment Terms",
            topic="PAYMENT_TERMS",
            authority_class="governing_agreement",
            content="Customer shall pay invoices within thirty (30) days ('Net 30').",
            structured_slots={"net_days": 30},
            is_active=True
        )
        self.db.add(cl_msa)

        # Amendment #1 (Net 45)
        amd = Agreement(
            tenant_id="tenant_test",
            title="Acme Corp - Amendment #1",
            instrument_type="amendment",
            counterparty="VendorCorp",
            effective_date=datetime(2025, 1, 1),
            status="active"
        )
        self.db.add(amd)
        self.db.flush()

        cl_amd = Clause(
            tenant_id="tenant_test",
            agreement_id=amd.id,
            section="Amendment Section 1",
            title="Amended Payment Terms",
            topic="PAYMENT_TERMS",
            authority_class="amendment",
            content="Section 4.1 is amended to Net 45 days.",
            structured_slots={"net_days": 45},
            is_active=True
        )
        self.db.add(cl_amd)

        # Relation: amd AMENDS msa
        rel = AgreementRelation(
            tenant_id="tenant_test",
            source_agreement_id=amd.id,
            target_agreement_id=msa.id,
            relation_type="AMENDS",
            effective_date=datetime(2025, 1, 1),
            clause_scope="Section 4.1"
        )
        self.db.add(rel)
        self.db.commit()

        # Resolve as of 2025-06-01 -> Amendment should control
        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="VendorCorp",
            topic="PAYMENT_TERMS",
            as_of_date=datetime(2025, 6, 1)
        )
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["controlling_clause"]["section"], "Amendment Section 1")
        self.assertEqual(res["controlling_clause"]["structured_slots"]["net_days"], 45)

    def test_02_detect_contract_conflicts(self):
        """Verify that conflicting slot values across active instruments are flagged."""
        ag1 = Agreement(
            tenant_id="tenant_test",
            title="Master Services Agreement",
            instrument_type="master_services_agreement",
            counterparty="DualVendor",
            effective_date=datetime(2024, 1, 1),
            status="active"
        )
        ag2 = Agreement(
            tenant_id="tenant_test",
            title="Cloud SOW #2",
            instrument_type="statement_of_work",
            counterparty="DualVendor",
            effective_date=datetime(2024, 6, 1),
            status="active"
        )
        self.db.add_all([ag1, ag2])
        self.db.flush()

        cl1 = Clause(
            tenant_id="tenant_test",
            agreement_id=ag1.id,
            section="Section 4.1",
            title="MSA Payment Terms",
            topic="PAYMENT_TERMS",
            content="Customer pays within thirty (30) days ('Net 30').",
            structured_slots={"net_days": 30},
            is_active=True
        )
        cl2 = Clause(
            tenant_id="tenant_test",
            agreement_id=ag2.id,
            section="Section 5.1",
            title="SOW Payment Terms",
            topic="PAYMENT_TERMS",
            content="Invoices payable within forty-five (45) days ('Net 45').",
            structured_slots={"net_days": 45},
            is_active=True
        )
        self.db.add_all([cl1, cl2])
        self.db.commit()

        conflicts = detect_contract_conflicts(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="DualVendor"
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["conflict_key"], "net_days")
        self.assertEqual(conflicts[0]["clause_a"]["value"], 30)
        self.assertEqual(conflicts[0]["clause_b"]["value"], 45)


if __name__ == "__main__":
    unittest.main()
