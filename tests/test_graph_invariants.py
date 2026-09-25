"""
tests/test_graph_invariants.py
==============================
Rigid, falsifiable Golden Graph Invariant tests for KruschBiz:
  1. Proposed edge never silently controls (auto-extracted relations stay advisory;
     resolver only walks human-confirmed edges; once confirmed, edge controls).
  2. Unexecuted draft cannot defeat executed agreement (execution_status='draft'
     cannot supersede, amend, or outrank execution_status='executed').
  3. Multi-hop amendment chain walk (Amendment 2 beats Amendment 1 and MSA with
     deterministic slot inheritance and 2-hop trace).
  4. Schedule / SOW cannot outrank governing body on core legal governance
     (MSA governs liability/indemnity; SOW governs pricing/fees).
  5. Immutable ResolutionTraceRecord persistence and API audit query.
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
from src.backend.db import (
    Agreement,
    AgreementRelation,
    Clause,
    ResolutionTraceRecord,
    init_db,
)
from src.backend.main import app, get_db
from src.backend.resolver import (
    detect_contract_conflicts,
    resolve_controlling_clause,
)


class TestGraphInvariants(unittest.TestCase):

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

    def tearDown(self):
        self.db.close()

    def test_01_proposed_edge_never_silently_controls(self):
        """
        Invariant: Auto-extracted relations with status='proposed' must NEVER silently
        control the precedence DAG. Only confirmed edges control.
        """
        msa = Agreement(
            tenant_id="tenant_inv",
            title="SaaS Master Agreement",
            instrument_type="master_agreement",
            counterparty="Apex Dynamics Inc",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(msa)
        self.db.flush()

        cl_msa = Clause(
            tenant_id="tenant_inv",
            agreement_id=msa.id,
            section="Section 4.1",
            title="Invoicing Terms",
            topic="PAYMENT_TERMS",
            authority_class="governing_agreement",
            content="Customer shall pay all invoices within Net 30 days.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        self.db.add(cl_msa)

        amd = Agreement(
            tenant_id="tenant_inv",
            title="Apex Amendment #1",
            instrument_type="amendment",
            counterparty="Apex Dynamics Inc",
            effective_date=datetime(2024, 6, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(amd)
        self.db.flush()

        cl_amd = Clause(
            tenant_id="tenant_inv",
            agreement_id=amd.id,
            section="Amendment 1.1",
            title="Amended Invoicing",
            topic="PAYMENT_TERMS",
            authority_class="amendment",
            content="Section 4.1 is hereby amended: Payment shall be Net 60 days.",
            structured_slots={"net_days": 60},
            is_active=True
        )
        self.db.add(cl_amd)

        # Proposed relation edge (NOT yet confirmed by human)
        rel = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=amd.id,
            target_agreement_id=msa.id,
            relation_type="AMENDS",
            effective_date=datetime(2024, 6, 1),
            clause_scope="Section 4.1",
            status="proposed",
            confidence=0.88,
            notes='{"status": "proposed", "source_excerpt": "Section 4.1 is hereby amended"}'
        )
        self.db.add(rel)
        self.db.commit()

        # Step A: Query while relation is 'proposed'
        res_before = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Apex Dynamics Inc",
            topic="PAYMENT_TERMS",
            as_of_date="2025-01-01"
        )

        # Proposed relation must NOT control! Base MSA remains controlling
        self.assertEqual(res_before["status"], "resolved")
        self.assertEqual(res_before["controlling_clause"]["section"], "Section 4.1")
        self.assertEqual(res_before["controlling_clause"]["structured_slots"]["net_days"], 30)
        self.assertGreaterEqual(len(res_before["proposed_relations_advisory"]), 1)
        self.assertEqual(res_before["proposed_relations_advisory"][0]["relation_id"], rel.id)

        # Step B: Confirm relation edge via API or model
        rel_db = self.db.query(AgreementRelation).filter(AgreementRelation.id == rel.id).first()
        rel_db.status = "confirmed"
        self.db.commit()

        # Step C: Query after human confirmation
        res_after = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Apex Dynamics Inc",
            topic="PAYMENT_TERMS",
            as_of_date="2025-01-01"
        )

        # Now Amendment #1 controls!
        self.assertEqual(res_after["status"], "resolved")
        self.assertEqual(res_after["controlling_clause"]["section"], "Amendment 1.1")
        self.assertEqual(res_after["controlling_clause"]["structured_slots"]["net_days"], 60)
        self.assertEqual(len(res_after["amendment_trail"]), 1)
        self.assertEqual(res_after["amendment_trail"][0]["relation"], "AMENDS")

    def test_02_unexecuted_draft_cannot_defeat_executed_agreement(self):
        """
        Invariant: An unexecuted draft (execution_status='draft') cannot supersede,
        amend, or defeat an executed agreement (execution_status='executed').
        """
        msa_executed = Agreement(
            tenant_id="tenant_inv",
            title="Executed Cloud Agreement",
            instrument_type="master_agreement",
            counterparty="Zenith Cloud Corp",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(msa_executed)
        self.db.flush()

        cl_executed = Clause(
            tenant_id="tenant_inv",
            agreement_id=msa_executed.id,
            section="Section 12.1",
            title="Limitation of Liability",
            topic="LIMITATION_OF_LIABILITY",
            authority_class="governing_agreement",
            content="Total aggregate liability is capped at $500,000.",
            structured_slots={"cap_amount": 500000},
            is_active=True
        )
        self.db.add(cl_executed)

        # Later dated draft agreement claiming to supersede
        draft_agreement = Agreement(
            tenant_id="tenant_inv",
            title="Proposed 2025 Restated Agreement (DRAFT)",
            instrument_type="master_agreement",
            counterparty="Zenith Cloud Corp",
            effective_date=datetime(2024, 11, 1),
            execution_status="draft",
            status="active"
        )
        self.db.add(draft_agreement)
        self.db.flush()

        cl_draft = Clause(
            tenant_id="tenant_inv",
            agreement_id=draft_agreement.id,
            section="Section 12.1",
            title="Limitation of Liability",
            topic="LIMITATION_OF_LIABILITY",
            authority_class="governing_agreement",
            content="Total aggregate liability is capped at $100,000.",
            structured_slots={"cap_amount": 100000},
            is_active=True
        )
        self.db.add(cl_draft)

        rel = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=draft_agreement.id,
            target_agreement_id=msa_executed.id,
            relation_type="SUPERSEDES",
            effective_date=datetime(2024, 11, 1),
            status="accepted"
        )
        self.db.add(rel)
        self.db.commit()

        # Query controlling clause as of 2025
        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Zenith Cloud Corp",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2025-01-01"
        )

        # Executed agreement MUST win; draft cannot supersede executed contract
        self.assertEqual(res["status"], "resolved")
        self.assertEqual(res["controlling_clause"]["agreement_id"], msa_executed.id)
        self.assertEqual(res["controlling_clause"]["structured_slots"]["cap_amount"], 500000)

    def test_03_multihop_amendment_chain_amendment_2_beats_msa(self):
        """
        Invariant: Multi-hop amendment chains (MSA -> Amd 1 -> Amd 2) must walk
        lineage correctly, inheriting unmodified slots and allowing leaf node to control.
        """
        msa = Agreement(
            tenant_id="tenant_inv",
            title="Global Services Agreement",
            instrument_type="master_agreement",
            counterparty="OmniCorp Global",
            effective_date=datetime(2022, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(msa)
        self.db.flush()

        cl_msa_pay = Clause(
            tenant_id="tenant_inv",
            agreement_id=msa.id,
            section="Section 3.1",
            title="Payment",
            topic="PAYMENT_TERMS",
            content="Payment is Net 30 days. Late penalty is 1.0% per month.",
            structured_slots={"net_days": 30, "late_penalty_pct": 1.0},
            is_active=True
        )
        cl_msa_cap = Clause(
            tenant_id="tenant_inv",
            agreement_id=msa.id,
            section="Section 9.1",
            title="Liability Cap",
            topic="LIMITATION_OF_LIABILITY",
            content="Liability is capped at $1,000,000.",
            structured_slots={"cap_amount": 1000000},
            is_active=True
        )
        self.db.add_all([cl_msa_pay, cl_msa_cap])

        amd1 = Agreement(
            tenant_id="tenant_inv",
            title="OmniCorp Amendment #1",
            instrument_type="amendment",
            counterparty="OmniCorp Global",
            effective_date=datetime(2023, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(amd1)
        self.db.flush()

        cl_amd1 = Clause(
            tenant_id="tenant_inv",
            agreement_id=amd1.id,
            section="Amd 1 - Sec 3.1",
            title="Payment Update",
            topic="PAYMENT_TERMS",
            content="Section 3.1 is amended to Net 45 days.",
            structured_slots={"net_days": 45},
            is_active=True
        )
        self.db.add(cl_amd1)

        rel1 = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=amd1.id,
            target_agreement_id=msa.id,
            relation_type="AMENDS",
            effective_date=datetime(2023, 1, 1),
            clause_scope="Section 3.1",
            status="confirmed"
        )
        self.db.add(rel1)

        amd2 = Agreement(
            tenant_id="tenant_inv",
            title="OmniCorp Amendment #2",
            instrument_type="amendment",
            counterparty="OmniCorp Global",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(amd2)
        self.db.flush()

        cl_amd2 = Clause(
            tenant_id="tenant_inv",
            agreement_id=amd2.id,
            section="Amd 2 - Sec 3.1",
            title="Further Payment Update",
            topic="PAYMENT_TERMS",
            content="Section 3.1 is further amended to Net 60 days.",
            structured_slots={"net_days": 60},
            is_active=True
        )
        self.db.add(cl_amd2)

        rel2 = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=amd2.id,
            target_agreement_id=amd1.id,
            relation_type="AMENDS",
            effective_date=datetime(2024, 1, 1),
            clause_scope="ALL",
            status="confirmed"
        )
        self.db.add(rel2)
        self.db.commit()

        # Step 1: Query PAYMENT_TERMS as of 2024
        res_pay = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="OmniCorp Global",
            topic="PAYMENT_TERMS",
            as_of_date="2024-06-01"
        )

        self.assertEqual(res_pay["status"], "resolved")
        self.assertEqual(res_pay["controlling_clause"]["agreement_id"], amd2.id)
        self.assertEqual(res_pay["controlling_clause"]["section"], "Amd 2 - Sec 3.1")
        self.assertEqual(res_pay["controlling_clause"]["structured_slots"]["net_days"], 60)
        # Inherited unmodified slot from base MSA:
        self.assertEqual(res_pay["controlling_clause"]["structured_slots"].get("late_penalty_pct"), 1.0)
        # Verify 2-hop amendment trail
        self.assertEqual(len(res_pay["amendment_trail"]), 2)

        # Step 2: Query LIMITATION_OF_LIABILITY (unaffected by amendments)
        res_liab = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="OmniCorp Global",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_liab["status"], "resolved")
        self.assertEqual(res_liab["controlling_clause"]["agreement_id"], msa.id)
        self.assertEqual(res_liab["controlling_clause"]["structured_slots"]["cap_amount"], 1000000)

    def test_04_schedule_cannot_outrank_body_on_legal_governance(self):
        """
        Invariant: A Statement of Work or Schedule cannot outrank the Master Agreement
        on legal governance (LIMITATION_OF_LIABILITY, GOVERNING_LAW), but controls for FEES/PAYMENT.
        """
        msa = Agreement(
            tenant_id="tenant_inv",
            title="Master Enterprise Agreement",
            instrument_type="master_agreement",
            counterparty="Vanguard Systems",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(msa)
        self.db.flush()

        cl_msa_liab = Clause(
            tenant_id="tenant_inv",
            agreement_id=msa.id,
            section="Section 10.1",
            title="Limitation of Liability",
            topic="LIMITATION_OF_LIABILITY",
            content="Total aggregate liability is capped at $2,000,000.",
            structured_slots={"cap_amount": 2000000},
            is_active=True
        )
        self.db.add(cl_msa_liab)

        sow = Agreement(
            tenant_id="tenant_inv",
            title="SOW #1 - Infrastructure Migration",
            instrument_type="statement_of_work",
            counterparty="Vanguard Systems",
            effective_date=datetime(2024, 2, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(sow)
        self.db.flush()

        # SOW attempts to cap liability at $50k and sets project fees at $120k
        cl_sow_liab = Clause(
            tenant_id="tenant_inv",
            agreement_id=sow.id,
            section="SOW Section 8",
            title="SOW Liability Cap",
            topic="LIMITATION_OF_LIABILITY",
            content="Liability for this SOW is capped at $50,000.",
            structured_slots={"cap_amount": 50000},
            is_active=True
        )
        cl_sow_fee = Clause(
            tenant_id="tenant_inv",
            agreement_id=sow.id,
            section="SOW Section 4",
            title="Project Fees",
            topic="FEES",
            content="Fixed project fee is $120,000 payable upon milestone completion.",
            structured_slots={"fixed_fee": 120000},
            is_active=True
        )
        self.db.add_all([cl_sow_liab, cl_sow_fee])

        rel = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=sow.id,
            target_agreement_id=msa.id,
            relation_type="SCHEDULE_OF",
            effective_date=datetime(2024, 2, 1),
            status="confirmed"
        )
        self.db.add(rel)
        self.db.commit()

        # 1. LIMITATION_OF_LIABILITY -> Master Agreement controls over SOW
        res_liab = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Vanguard Systems",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_liab["status"], "resolved")
        self.assertEqual(res_liab["controlling_clause"]["agreement_id"], msa.id)
        self.assertEqual(res_liab["controlling_clause"]["structured_slots"]["cap_amount"], 2000000)

        # 2. FEES -> SOW controls over Master Agreement
        res_fee = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Vanguard Systems",
            topic="FEES",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_fee["status"], "resolved")
        self.assertEqual(res_fee["controlling_clause"]["agreement_id"], sow.id)
        self.assertEqual(res_fee["controlling_clause"]["structured_slots"]["fixed_fee"], 120000)

    def test_05_resolution_trace_persistence_and_api(self):
        """
        Invariant: Every precedence graph resolution persists an immutable
        ResolutionTraceRecord in the database with full hop history, accessible via API.
        """
        ag = Agreement(
            tenant_id="tenant_inv",
            title="Consulting Framework Agreement",
            instrument_type="master_agreement",
            counterparty="Deloitte Advisory LLP",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(ag)
        self.db.flush()

        cl = Clause(
            tenant_id="tenant_inv",
            agreement_id=ag.id,
            section="Section 5.1",
            title="Governing Law",
            topic="GOVERNING_LAW",
            content="This agreement shall be governed by the laws of California.",
            structured_slots={"jurisdiction": "California"},
            is_active=True
        )
        self.db.add(cl)
        self.db.commit()

        # Perform resolution
        res = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Deloitte Advisory LLP",
            topic="GOVERNING_LAW",
            as_of_date="2024-05-01"
        )
        self.assertEqual(res["status"], "resolved")
        self.assertIn("resolution_trace", res)
        trace_id = res["resolution_trace"]["trace_id"]

        # Verify DB persistence
        trace_record = self.db.query(ResolutionTraceRecord).filter(
            ResolutionTraceRecord.id == trace_id
        ).first()
        self.assertIsNotNone(trace_record)
        self.assertEqual(trace_record.counterparty, "Deloitte Advisory LLP")
        self.assertEqual(trace_record.topic, "GOVERNING_LAW")
        self.assertEqual(trace_record.status, "resolved")
        self.assertEqual(trace_record.controlling_clause_id, cl.id)

        # Test REST API GET /api/resolution-traces
        resp = self.client.get(
            "/api/resolution-traces?counterparty=Deloitte Advisory LLP",
            headers={"X-Tenant-ID": "tenant_inv"}
        )
        self.assertEqual(resp.status_code, 200)
        traces = resp.json()
        self.assertGreaterEqual(len(traces), 1)
        self.assertEqual(traces[0]["id"], trace_id)
        self.assertEqual(traces[0]["topic"], "GOVERNING_LAW")

        # Test REST API GET /api/agreements/conflicts
        resp_conf = self.client.get(
            "/api/agreements/conflicts?counterparty=Deloitte Advisory LLP",
            headers={"X-Tenant-ID": "tenant_inv"}
        )
        self.assertEqual(resp_conf.status_code, 200)
        self.assertIn("conflicts", resp_conf.json())


if __name__ == "__main__":
    unittest.main()
