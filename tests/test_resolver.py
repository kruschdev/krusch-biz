"""
tests/test_resolver.py
======================
Comprehensive unit tests for the true DAG controlling-document resolver
and post-resolution conflict detection engine.

Test Matrix:
  1. Partial amendment (scoped AMENDS modifies §4.1 payment, but leaves §12.1 liability cap untouched in MSA)
  2. Circular AMENDS protection (graph traversal breaks cycles gracefully without crashing or looping)
  3. Expired instrument exclusion (instrument with expiration_date <= as_of is excluded even if status='active')
  4. SOW vs MSA order of precedence (SOW controls for fees/payment; MSA controls for liability under SCHEDULE_OF)
  5. Strict counterparty isolation (zero cross-vendor leakage, returns 'not_found' when party doesn't match)
  6. Same-day / unresolved instruments return 'ambiguous' with confidence 0.0 (no fabricated winners)
  7. Multi-hop amendment chain (MSA -> Amendment 1 -> Amendment 2 resolves to Amendment 2 with full trail)
  8. Post-resolution conflict detection (surfaces divergent terms across live active instruments)
"""

import os
import sys
import unittest
from datetime import date, datetime

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
from src.backend.db import Agreement, AgreementRelation, Clause, init_db
from src.backend.resolver import (
    detect_contract_conflicts,
    normalize_party_name,
    resolve_controlling_clause,
)


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
        self.db.query(AgreementRelation).delete()
        self.db.query(Clause).delete()
        self.db.query(Agreement).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_partial_amendment(self):
        """
        Amendment modifies Section 4.1 (payment terms to Net 45),
        while Section 12.1 (liability cap at $500k) remains controlling in the MSA.
        """
        msa = Agreement(
            tenant_id="tenant_alpha",
            title="CloudScale Master Agreement",
            instrument_type="master_services_agreement",
            counterparty="CloudScale AI LLC",
            effective_date=datetime(2023, 1, 1),
            status="active"
        )
        self.db.add(msa)
        self.db.flush()

        # MSA clauses
        cl_msa_payment = Clause(
            tenant_id="tenant_alpha",
            agreement_id=msa.id,
            section="Section 4.1",
            title="Payment Terms",
            topic="PAYMENT_TERMS",
            authority_class="governing_agreement",
            content="Customer pays invoices within thirty (30) days ('Net 30').",
            structured_slots={"net_days": 30},
            is_active=True
        )
        cl_msa_liability = Clause(
            tenant_id="tenant_alpha",
            agreement_id=msa.id,
            section="Section 12.1",
            title="Limitation of Liability",
            topic="LIMITATION_OF_LIABILITY",
            authority_class="governing_agreement",
            content="Aggregate liability under this agreement is capped at $500,000.",
            structured_slots={"cap_amount": 500000},
            is_active=True
        )
        self.db.add_all([cl_msa_payment, cl_msa_liability])

        # Amendment #1 (ONLY amends Section 4.1)
        amd = Agreement(
            tenant_id="tenant_alpha",
            title="CloudScale Amendment #1",
            instrument_type="amendment",
            counterparty="CloudScale AI LLC",
            effective_date=datetime(2024, 6, 1),
            status="active"
        )
        self.db.add(amd)
        self.db.flush()

        cl_amd_payment = Clause(
            tenant_id="tenant_alpha",
            agreement_id=amd.id,
            section="Amendment Section 1",
            title="Amended Payment Terms",
            topic="PAYMENT_TERMS",
            authority_class="amendment",
            content="Section 4.1 is amended to Net 45 days.",
            structured_slots={"net_days": 45},
            is_active=True
        )
        self.db.add(cl_amd_payment)

        # Scoped relation: amd AMENDS msa ONLY for Section 4.1
        rel = AgreementRelation(
            tenant_id="tenant_alpha",
            source_agreement_id=amd.id,
            target_agreement_id=msa.id,
            relation_type="AMENDS",
            effective_date=datetime(2024, 6, 1),
            clause_scope="Section 4.1"
        )
        self.db.add(rel)
        self.db.commit()

        # 1. Resolve PAYMENT_TERMS -> Should resolve to Amendment #1 (Net 45)
        res_pay = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_alpha",
            counterparty="CloudScale AI",
            topic="PAYMENT_TERMS",
            as_of_date="2025-01-01"
        )
        self.assertEqual(res_pay["status"], "resolved")
        self.assertEqual(res_pay["controlling_clause"]["section"], "Amendment Section 1")
        self.assertEqual(res_pay["controlling_clause"]["structured_slots"]["net_days"], 45)
        self.assertEqual(res_pay["confidence"], 1.0)
        self.assertEqual(len(res_pay["amendment_trail"]), 1)

        # 2. Resolve LIMITATION_OF_LIABILITY -> Should remain Section 12.1 in MSA ($500k)!
        res_liab = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_alpha",
            counterparty="CloudScale AI",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2025-01-01"
        )
        self.assertEqual(res_liab["status"], "resolved")
        self.assertEqual(res_liab["controlling_clause"]["section"], "Section 12.1")
        self.assertEqual(res_liab["controlling_clause"]["structured_slots"]["cap_amount"], 500000)
        self.assertEqual(res_liab["confidence"], 0.85)
        self.assertEqual(len(res_liab["amendment_trail"]), 0)

    def test_02_circular_amends_protection(self):
        """Verify that cyclic AMENDS relations do not trigger infinite recursion."""
        ag1 = Agreement(
            tenant_id="tenant_test",
            title="Agreement A",
            instrument_type="amendment",
            counterparty="CycleCorp",
            effective_date=datetime(2024, 1, 1),
            status="active"
        )
        ag2 = Agreement(
            tenant_id="tenant_test",
            title="Agreement B",
            instrument_type="amendment",
            counterparty="CycleCorp",
            effective_date=datetime(2024, 2, 1),
            status="active"
        )
        self.db.add_all([ag1, ag2])
        self.db.flush()

        cl1 = Clause(
            tenant_id="tenant_test",
            agreement_id=ag1.id,
            section="Section 1",
            topic="PAYMENT_TERMS",
            content="Terms A: Net 30.",
            is_active=True
        )
        cl2 = Clause(
            tenant_id="tenant_test",
            agreement_id=ag2.id,
            section="Section 1",
            topic="PAYMENT_TERMS",
            content="Terms B: Net 45.",
            is_active=True
        )
        self.db.add_all([cl1, cl2])

        # Circular edges: ag2 AMENDS ag1 AND ag1 AMENDS ag2
        rel1 = AgreementRelation(
            tenant_id="tenant_test",
            source_agreement_id=ag2.id,
            target_agreement_id=ag1.id,
            relation_type="AMENDS",
            effective_date=datetime(2024, 2, 1)
        )
        rel2 = AgreementRelation(
            tenant_id="tenant_test",
            source_agreement_id=ag1.id,
            target_agreement_id=ag2.id,
            relation_type="AMENDS",
            effective_date=datetime(2024, 3, 1)
        )
        self.db.add_all([rel1, rel2])
        self.db.commit()

        # Should terminate cleanly without stack overflow
        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="CycleCorp",
            topic="PAYMENT_TERMS",
            as_of_date="2025-01-01"
        )
        self.assertIn(res["status"], ("resolved", "ambiguous"))

    def test_03_expired_instrument_excluded(self):
        """
        Verify that an agreement whose expiration_date <= as_of is excluded,
        even if its status column was left as 'active'.
        """
        expired_msa = Agreement(
            tenant_id="tenant_test",
            title="Legacy Expired MSA",
            instrument_type="master_services_agreement",
            counterparty="OldVendor Inc",
            effective_date=datetime(2020, 1, 1),
            expiration_date=datetime(2023, 1, 1),
            status="active"  # Stale active flag
        )
        self.db.add(expired_msa)
        self.db.flush()

        cl = Clause(
            tenant_id="tenant_test",
            agreement_id=expired_msa.id,
            section="Section 3.1",
            topic="PAYMENT_TERMS",
            content="Payment Net 15 days.",
            is_active=True
        )
        self.db.add(cl)
        self.db.commit()

        # As of 2024-01-01, the agreement is expired
        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="OldVendor",
            topic="PAYMENT_TERMS",
            as_of_date="2024-01-01"
        )
        self.assertEqual(res["status"], "all_authorities_superseded")
        self.assertIsNone(res["controlling_clause"])

    def test_04_sow_controls_fees_msa_controls_liability(self):
        """
        Verify SOW vs MSA order of precedence under SCHEDULE_OF:
        SOW controls for PAYMENT_TERMS/FEES; MSA controls for LIMITATION_OF_LIABILITY.
        """
        msa = Agreement(
            tenant_id="tenant_test",
            title="Global Services MSA",
            instrument_type="master_services_agreement",
            counterparty="Apex Solutions LLC",
            effective_date=datetime(2024, 1, 1),
            status="active"
        )
        sow = Agreement(
            tenant_id="tenant_test",
            title="Statement of Work #1",
            instrument_type="statement_of_work",
            counterparty="Apex Solutions LLC",
            effective_date=datetime(2024, 2, 1),
            status="active"
        )
        self.db.add_all([msa, sow])
        self.db.flush()

        # MSA provisions: Net 30 payment, $1M liability cap
        cl_msa_pay = Clause(
            tenant_id="tenant_test",
            agreement_id=msa.id,
            section="Section 4.1",
            topic="PAYMENT_TERMS",
            content="Standard MSA payment is Net 30 days.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        cl_msa_liab = Clause(
            tenant_id="tenant_test",
            agreement_id=msa.id,
            section="Section 9.1",
            topic="LIMITATION_OF_LIABILITY",
            content="MSA Liability cap is $1,000,000.",
            structured_slots={"cap_amount": 1000000},
            is_active=True
        )

        # SOW provisions: Project-specific Net 15 milestone payment, attempted $50k liability cap
        cl_sow_pay = Clause(
            tenant_id="tenant_test",
            agreement_id=sow.id,
            section="Schedule B",
            topic="PAYMENT_TERMS",
            content="SOW fee milestones payable Net 15 days.",
            structured_slots={"net_days": 15},
            is_active=True
        )
        cl_sow_liab = Clause(
            tenant_id="tenant_test",
            agreement_id=sow.id,
            section="Schedule D",
            topic="LIMITATION_OF_LIABILITY",
            content="Project liability limited to $50,000.",
            structured_slots={"cap_amount": 50000},
            is_active=True
        )
        self.db.add_all([cl_msa_pay, cl_msa_liab, cl_sow_pay, cl_sow_liab])

        # Relation: sow is SCHEDULE_OF msa
        rel = AgreementRelation(
            tenant_id="tenant_test",
            source_agreement_id=sow.id,
            target_agreement_id=msa.id,
            relation_type="SCHEDULE_OF",
            effective_date=datetime(2024, 2, 1)
        )
        self.db.add(rel)
        self.db.commit()

        # 1. PAYMENT_TERMS: SOW should take precedence (Net 15)
        res_pay = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="Apex Solutions",
            topic="PAYMENT_TERMS",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_pay["status"], "resolved")
        self.assertEqual(res_pay["controlling_clause"]["agreement_title"], "Statement of Work #1")
        self.assertEqual(res_pay["controlling_clause"]["structured_slots"]["net_days"], 15)

        # 2. LIMITATION_OF_LIABILITY: MSA should take precedence ($1,000,000)
        res_liab = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="Apex Solutions",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_liab["status"], "resolved")
        self.assertEqual(res_liab["controlling_clause"]["agreement_title"], "Global Services MSA")
        self.assertEqual(res_liab["controlling_clause"]["structured_slots"]["cap_amount"], 1000000)

    def test_05_strict_counterparty_isolation(self):
        """
        Verify ZERO cross-vendor data leakage:
        Agreements belonging to Vendor A are NEVER returned for Vendor B inquiries.
        """
        ag_alpha = Agreement(
            tenant_id="tenant_sec",
            title="Vendor Alpha Confidential Agreement",
            instrument_type="master_services_agreement",
            counterparty="Alpha Technologies Inc",
            effective_date=datetime(2024, 1, 1),
            status="active"
        )
        self.db.add(ag_alpha)
        self.db.flush()

        cl = Clause(
            tenant_id="tenant_sec",
            agreement_id=ag_alpha.id,
            section="Section 4",
            topic="PAYMENT_TERMS",
            content="Alpha terms: Net 60.",
            is_active=True
        )
        self.db.add(cl)
        self.db.commit()

        # Query for totally different Vendor Beta
        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_sec",
            counterparty="Beta Logistics Corp",
            topic="PAYMENT_TERMS",
            as_of_date="2024-06-01"
        )
        # Must return 'not_found' immediately — ZERO tenant-wide fallback
        self.assertEqual(res["status"], "not_found")
        self.assertIsNone(res["controlling_clause"])

    def test_06_same_day_instruments_unresolved_is_ambiguous(self):
        """
        When two concurrently active instruments have conflicting terms
        without an explicit AMENDS or SUPERSEDES edge, the resolver must return
        'ambiguous' with confidence 0.0 rather than fabricating a winner.
        """
        ag1 = Agreement(
            tenant_id="tenant_test",
            title="Agreement Version Alpha",
            instrument_type="governing_agreement",
            counterparty="DualTrack Corp",
            effective_date=datetime(2024, 5, 1),
            status="active"
        )
        ag2 = Agreement(
            tenant_id="tenant_test",
            title="Agreement Version Beta",
            instrument_type="governing_agreement",
            counterparty="DualTrack Corp",
            effective_date=datetime(2024, 5, 1),
            status="active"
        )
        self.db.add_all([ag1, ag2])
        self.db.flush()

        cl1 = Clause(
            tenant_id="tenant_test",
            agreement_id=ag1.id,
            section="Section 4.1",
            topic="PAYMENT_TERMS",
            content="Payable in Net 30.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        cl2 = Clause(
            tenant_id="tenant_test",
            agreement_id=ag2.id,
            section="Section 4.1",
            topic="PAYMENT_TERMS",
            content="Payable in Net 60.",
            structured_slots={"net_days": 60},
            is_active=True
        )
        self.db.add_all([cl1, cl2])
        self.db.commit()

        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="DualTrack Corp",
            topic="PAYMENT_TERMS",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res["status"], "ambiguous")
        self.assertIsNone(res["controlling_clause"])
        self.assertEqual(res["confidence"], 0.0)
        self.assertEqual(len(res["conflicting_candidates"]), 2)

    def test_07_multi_hop_amendment_chain(self):
        """
        Trace MSA (2021) -> Amendment 1 (2023) -> Amendment 2 (2025):
        Resolves to Amendment 2 with complete 2-hop provenance trail.
        """
        msa = Agreement(
            tenant_id="tenant_test",
            title="Base MSA 2021",
            instrument_type="master_services_agreement",
            counterparty="ChainCorp",
            effective_date=datetime(2021, 1, 1),
            status="active"
        )
        amd1 = Agreement(
            tenant_id="tenant_test",
            title="Amendment No. 1",
            instrument_type="amendment",
            counterparty="ChainCorp",
            effective_date=datetime(2023, 1, 1),
            status="active"
        )
        amd2 = Agreement(
            tenant_id="tenant_test",
            title="Amendment No. 2",
            instrument_type="amendment",
            counterparty="ChainCorp",
            effective_date=datetime(2025, 1, 1),
            status="active"
        )
        self.db.add_all([msa, amd1, amd2])
        self.db.flush()

        cl0 = Clause(
            tenant_id="tenant_test",
            agreement_id=msa.id,
            section="Section 4.1",
            topic="PAYMENT_TERMS",
            content="Net 30.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        cl1 = Clause(
            tenant_id="tenant_test",
            agreement_id=amd1.id,
            section="Amd1 Sec 2",
            topic="PAYMENT_TERMS",
            content="Amended to Net 45.",
            structured_slots={"net_days": 45},
            is_active=True
        )
        cl2 = Clause(
            tenant_id="tenant_test",
            agreement_id=amd2.id,
            section="Amd2 Sec 3",
            topic="PAYMENT_TERMS",
            content="Amended to Net 60.",
            structured_slots={"net_days": 60},
            is_active=True
        )
        self.db.add_all([cl0, cl1, cl2])

        # Relations: amd1 AMENDS msa; amd2 AMENDS amd1
        rel1 = AgreementRelation(
            tenant_id="tenant_test",
            source_agreement_id=amd1.id,
            target_agreement_id=msa.id,
            relation_type="AMENDS",
            clause_scope="Section 4.1",
            effective_date=datetime(2023, 1, 1)
        )
        rel2 = AgreementRelation(
            tenant_id="tenant_test",
            source_agreement_id=amd2.id,
            target_agreement_id=amd1.id,
            relation_type="AMENDS",
            clause_scope="Amd1 Sec 2",
            effective_date=datetime(2025, 1, 1)
        )
        self.db.add_all([rel1, rel2])
        self.db.commit()

        # 1. As of 2022 -> Base MSA controls (Net 30)
        res_2022 = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="ChainCorp",
            topic="PAYMENT_TERMS",
            as_of_date="2022-01-01"
        )
        self.assertEqual(res_2022["status"], "resolved")
        self.assertEqual(res_2022["controlling_clause"]["structured_slots"]["net_days"], 30)

        # 2. As of 2024 -> Amendment 1 controls (Net 45)
        res_2024 = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="ChainCorp",
            topic="PAYMENT_TERMS",
            as_of_date="2024-01-01"
        )
        self.assertEqual(res_2024["status"], "resolved")
        self.assertEqual(res_2024["controlling_clause"]["structured_slots"]["net_days"], 45)
        self.assertEqual(len(res_2024["amendment_trail"]), 1)

        # 3. As of 2026 -> Amendment 2 controls (Net 60, 2-hop trail)
        res_2026 = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_test",
            counterparty="ChainCorp",
            topic="PAYMENT_TERMS",
            as_of_date="2026-01-01"
        )
        self.assertEqual(res_2026["status"], "resolved")
        self.assertEqual(res_2026["controlling_clause"]["structured_slots"]["net_days"], 60)
        self.assertEqual(len(res_2026["amendment_trail"]), 2)
        self.assertEqual(res_2026["confidence"], 1.0)

    def test_08_post_resolution_detect_conflicts(self):
        """Verify that detect_contract_conflicts catches ambiguous unresolved topics."""
        ag1 = Agreement(
            tenant_id="tenant_conflict",
            title="Agreement Alpha",
            instrument_type="master_services_agreement",
            counterparty="ConflictVendor",
            effective_date=datetime(2024, 1, 1),
            status="active"
        )
        ag2 = Agreement(
            tenant_id="tenant_conflict",
            title="Agreement Beta",
            instrument_type="master_services_agreement",
            counterparty="ConflictVendor",
            effective_date=datetime(2024, 1, 1),
            status="active"
        )
        self.db.add_all([ag1, ag2])
        self.db.flush()

        cl1 = Clause(
            tenant_id="tenant_conflict",
            agreement_id=ag1.id,
            section="Section 4",
            topic="PAYMENT_TERMS",
            content="Net 30.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        cl2 = Clause(
            tenant_id="tenant_conflict",
            agreement_id=ag2.id,
            section="Section 4",
            topic="PAYMENT_TERMS",
            content="Net 90.",
            structured_slots={"net_days": 90},
            is_active=True
        )
        self.db.add_all([cl1, cl2])
        self.db.commit()

        conflicts = detect_contract_conflicts(
            db=self.db,
            tenant_id="tenant_conflict",
            counterparty="ConflictVendor",
            as_of_date="2024-06-01"
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["topic"], "PAYMENT_TERMS")
        self.assertEqual(conflicts[0]["conflict_type"], "AMBIGUOUS_CONTROLLING_INSTRUMENT")


if __name__ == "__main__":
    unittest.main()
