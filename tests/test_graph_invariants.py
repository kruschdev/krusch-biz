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
    compute_clause_uid,
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

    def test_06_proposed_supersedes_never_changes_controlling_clause(self):
        """
        Invariant: Proposed SUPERSEDES relation edge must NEVER alter the controlling clause.
        Only once human-confirmed does it supersede the prior agreement.
        """
        ag1 = Agreement(
            tenant_id="tenant_inv",
            title="2023 Enterprise License Agreement",
            instrument_type="master_agreement",
            counterparty="Omega Analytics Corp",
            effective_date=datetime(2023, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(ag1)
        self.db.flush()

        cl1 = Clause(
            tenant_id="tenant_inv",
            agreement_id=ag1.id,
            section="Section 8.1",
            title="Liability Limitation",
            topic="LIMITATION_OF_LIABILITY",
            content="Total aggregate liability shall not exceed $1,000,000.",
            structured_slots={"cap_amount": 1000000.0},
            is_active=True
        )
        self.db.add(cl1)

        ag2 = Agreement(
            tenant_id="tenant_inv",
            title="2024 Restated Enterprise License Agreement",
            instrument_type="master_agreement",
            counterparty="Omega Analytics Corp",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(ag2)
        self.db.flush()

        cl2 = Clause(
            tenant_id="tenant_inv",
            agreement_id=ag2.id,
            section="Section 8.1",
            title="Amended Liability Limitation",
            topic="LIMITATION_OF_LIABILITY",
            content="Total aggregate liability shall not exceed $5,000,000.",
            structured_slots={"cap_amount": 5000000.0},
            is_active=True
        )
        self.db.add(cl2)

        # Proposed SUPERSEDES edge (not confirmed)
        rel_sup = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=ag2.id,
            target_agreement_id=ag1.id,
            relation_type="SUPERSEDES",
            effective_date=datetime(2024, 1, 1),
            clause_scope="ALL",
            status="proposed",
            confidence=0.95
        )
        self.db.add(rel_sup)
        self.db.commit()

        # Step A: While relation is proposed, ag1 is NOT superseded!
        res_before = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Omega Analytics Corp",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2024-06-01"
        )
        self.assertGreaterEqual(len(res_before["proposed_relations_advisory"]), 1)
        self.assertEqual(res_before["proposed_relations_advisory"][0]["relation_id"], rel_sup.id)
        if res_before.get("controlling_clause"):
            self.assertNotEqual(res_before["controlling_clause"]["structured_slots"].get("cap_amount"), 5000000.0)

        # Step B: Confirm relation
        rel_db = self.db.query(AgreementRelation).filter(AgreementRelation.id == rel_sup.id).first()
        rel_db.status = "confirmed"
        self.db.commit()

        # Step C: After human confirmation, ag2 unambiguously supersedes ag1
        res_after = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Omega Analytics Corp",
            topic="LIMITATION_OF_LIABILITY",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_after["status"], "resolved")
        self.assertEqual(res_after["controlling_clause"]["agreement_id"], ag2.id)
        self.assertEqual(res_after["controlling_clause"]["structured_slots"]["cap_amount"], 5000000.0)

    def test_07_draft_isolation_table_of_cases(self):
        """
        Invariant: Draft isolation table of cases.
        execution_status='draft' can NEVER win against execution_status='executed', period.
        """
        cases = [
            ("draft_amends_executed", "AMENDS"),
            ("draft_supersedes_executed", "SUPERSEDES"),
        ]
        for case_name, rel_type in cases:
            with self.subTest(case=case_name):
                # Setup executed base
                executed_ag = Agreement(
                    tenant_id="tenant_inv",
                    title=f"Base Executed Agreement ({case_name})",
                    instrument_type="master_agreement",
                    counterparty="DraftShield LLC",
                    effective_date=datetime(2024, 1, 1),
                    execution_status="executed",
                    status="active"
                )
                self.db.add(executed_ag)
                self.db.flush()

                executed_cl = Clause(
                    tenant_id="tenant_inv",
                    agreement_id=executed_ag.id,
                    section="Section 4.1",
                    title="Payment",
                    topic="PAYMENT_TERMS",
                    content="Payment Net 30 days.",
                    structured_slots={"net_days": 30},
                    is_active=True
                )
                self.db.add(executed_cl)

                # Setup draft challenger
                draft_ag = Agreement(
                    tenant_id="tenant_inv",
                    title=f"Draft Challenger ({case_name})",
                    instrument_type="amendment" if rel_type == "AMENDS" else "master_agreement",
                    counterparty="DraftShield LLC",
                    effective_date=datetime(2024, 6, 1),
                    execution_status="draft",
                    status="draft"
                )
                self.db.add(draft_ag)
                self.db.flush()

                draft_cl = Clause(
                    tenant_id="tenant_inv",
                    agreement_id=draft_ag.id,
                    section="Section 4.1",
                    title="Draft Payment",
                    topic="PAYMENT_TERMS",
                    content="Draft terms: Payment Net 90 days.",
                    structured_slots={"net_days": 90},
                    is_active=True
                )
                self.db.add(draft_cl)

                # Even if confirmed, a draft CANNOT supersede or amend executed
                rel_draft = AgreementRelation(
                    tenant_id="tenant_inv",
                    source_agreement_id=draft_ag.id,
                    target_agreement_id=executed_ag.id,
                    relation_type=rel_type,
                    clause_scope="ALL",
                    status="confirmed"
                )
                self.db.add(rel_draft)
                self.db.commit()

                res = resolve_controlling_clause(
                    db=self.db,
                    tenant_id="tenant_inv",
                    counterparty="DraftShield LLC",
                    topic="PAYMENT_TERMS",
                    as_of_date="2024-09-01"
                )
                self.assertEqual(res["status"], "resolved")
                self.assertEqual(res["controlling_clause"]["agreement_id"], executed_ag.id)
                self.assertEqual(res["controlling_clause"]["structured_slots"]["net_days"], 30)

                # Clean up for next case
                self.db.query(AgreementRelation).filter(AgreementRelation.tenant_id == "tenant_inv").delete()
                self.db.query(Clause).filter(Clause.tenant_id == "tenant_inv").delete()
                self.db.query(Agreement).filter(Agreement.tenant_id == "tenant_inv").delete()
                self.db.commit()

    def test_08_graph_cycles_self_loop_and_depth_cap(self):
        """
        Invariant: Graph cycle detection.
        1. Immediate self-loop (source_id == target_id) returns status='GRAPH_CYCLE'.
        2. Circular chain (A amends B, B amends A) returns status='GRAPH_CYCLE'.
        """
        # Case 1: Self-loop
        ag_self = Agreement(
            tenant_id="tenant_inv",
            title="Self Looping Agreement",
            instrument_type="master_agreement",
            counterparty="Ouroboros Corp",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(ag_self)
        self.db.flush()

        cl_self = Clause(
            tenant_id="tenant_inv",
            agreement_id=ag_self.id,
            section="Section 1",
            title="Loop Term",
            topic="PAYMENT_TERMS",
            content="Terms loop Net 30.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        self.db.add(cl_self)

        rel_self = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=ag_self.id,
            target_agreement_id=ag_self.id,
            relation_type="AMENDS",
            clause_scope="ALL",
            status="confirmed"
        )
        self.db.add(rel_self)
        self.db.commit()

        res_self = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Ouroboros Corp",
            topic="PAYMENT_TERMS",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_self["status"], "GRAPH_CYCLE")
        self.assertIn("Circular precedence dependency detected", res_self["resolution_rationale"])

        # Case 2: Multi-node circular loop (A amends B, B amends A)
        ag_b = Agreement(
            tenant_id="tenant_inv",
            title="Loop Peer Agreement",
            instrument_type="amendment",
            counterparty="Ouroboros Two Corp",
            effective_date=datetime(2024, 2, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(ag_b)
        self.db.flush()

        cl_b = Clause(
            tenant_id="tenant_inv",
            agreement_id=ag_b.id,
            section="Section 1",
            title="Amended Loop Term",
            topic="PAYMENT_TERMS",
            content="Terms loop Net 45.",
            structured_slots={"net_days": 45},
            is_active=True
        )
        self.db.add(cl_b)

        ag_a = Agreement(
            tenant_id="tenant_inv",
            title="Loop Base Agreement",
            instrument_type="master_agreement",
            counterparty="Ouroboros Two Corp",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(ag_a)
        self.db.flush()

        cl_a = Clause(
            tenant_id="tenant_inv",
            agreement_id=ag_a.id,
            section="Section 1",
            title="Base Loop Term",
            topic="PAYMENT_TERMS",
            content="Terms loop Net 30.",
            structured_slots={"net_days": 30},
            is_active=True
        )
        self.db.add(cl_a)

        rel_ab = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=ag_b.id,
            target_agreement_id=ag_a.id,
            relation_type="AMENDS",
            clause_scope="ALL",
            status="confirmed"
        )
        rel_ba = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=ag_a.id,
            target_agreement_id=ag_b.id,
            relation_type="AMENDS",
            clause_scope="ALL",
            status="confirmed"
        )
        self.db.add_all([rel_ab, rel_ba])
        self.db.commit()

        res_cycle = resolve_controlling_clause(
            db=self.db,
            tenant_id="tenant_inv",
            counterparty="Ouroboros Two Corp",
            topic="PAYMENT_TERMS",
            as_of_date="2024-06-01"
        )
        self.assertEqual(res_cycle["status"], "GRAPH_CYCLE")

    def test_09_clause_uid_schema_and_frozen_hash(self):
        """
        Invariant: clause_uid hash schema is documented and frozen.
        Changing the hashing inputs or truncation is a schema migration.
        Schema: sha256(f"{normalize_party_name(instrument_family)}|{canonical_topic.strip().upper()}|{json.dumps(clean_slots, sort_keys=True)}|{restates_clause_id or ''}")[:32]
        """
        # Test Case 1: Simple topic + family without slots
        uid_1 = compute_clause_uid(
            instrument_family="CloudScale AI LLC",
            canonical_topic="LIMITATION_OF_LIABILITY"
        )
        self.assertEqual(len(uid_1), 32)
        expected_1 = "caae434bc82052f510d1cae2bfab64f4"
        self.assertEqual(uid_1, expected_1, "clause_uid hash calculation regressed or mutated without a migration!")

        # Test Case 2: Topic + slots + restates pointer
        uid_2 = compute_clause_uid(
            instrument_family="Acme Corp, Inc.",
            canonical_topic="PAYMENT_TERMS",
            slot_signature={"net_days": 30, "late_interest_pct": 1.5},
            restates_clause_id=42
        )
        self.assertEqual(len(uid_2), 32)
        expected_2 = "e0c4dde095f10aed98a9a8394665a2f1"
        self.assertEqual(uid_2, expected_2, "clause_uid hash with slots and restates pointer regressed!")

    def test_10_ugly_real_pack(self):
        """
        Invariant: The Ugly Real Pack.
        Realistic multi-document family containing:
          - 2021 Stale MSA ($500k cap, Net 30, $100/hr)
          - 2023 Restated MSA (supersedes 2021 MSA, $1M cap, Net 45, $120/hr)
          - Amendment No. 1 (amends Restated MSA: Net 60 payment)
          - Amendment No. 2 (amends Restated MSA: liability cap raised to $2,000,000)
          - Amendment No. 3 (amends Amendment No. 1: payment terms restored to Net 30, 1.5% interest)
          - Draft Amendment No. 4 (unexecuted draft proposing $100k cap, Net 90; draft loses!)
          - Schedule A-1 (SOW overriding fee schedule to $150/hr, but MSA controls liability)
        """
        cp = "Titan Heavy Logistics Inc"

        # 1. 2021 Stale MSA
        msa_2021 = Agreement(
            tenant_id="tenant_inv",
            title="2021 Master Logistics Services Agreement",
            instrument_type="master_agreement",
            counterparty=cp,
            effective_date=datetime(2021, 1, 15),
            execution_status="executed",
            status="active"
        )
        self.db.add(msa_2021)
        self.db.flush()

        self.db.add_all([
            Clause(tenant_id="tenant_inv", agreement_id=msa_2021.id, section="Section 4.1", title="Payment", topic="PAYMENT_TERMS", authority_class="governing_agreement", content="Net 30 payment.", structured_slots={"net_days": 30}, is_active=True),
            Clause(tenant_id="tenant_inv", agreement_id=msa_2021.id, section="Section 8.1", title="Liability", topic="LIMITATION_OF_LIABILITY", authority_class="governing_agreement", content="Liability capped at $500,000.", structured_slots={"cap_amount": 500000.0}, is_active=True),
            Clause(tenant_id="tenant_inv", agreement_id=msa_2021.id, section="Section 3.1", title="Fees", topic="FEES", authority_class="governing_agreement", content="Standard hourly rate $100/hr.", structured_slots={"hourly_rate": 100}, is_active=True),
        ])

        # 2. 2023 Restated MSA (supersedes 2021 MSA)
        msa_2023 = Agreement(
            tenant_id="tenant_inv",
            title="2023 Amended and Restated Master Logistics Services Agreement",
            instrument_type="master_agreement",
            counterparty=cp,
            effective_date=datetime(2023, 1, 15),
            execution_status="executed",
            status="active"
        )
        self.db.add(msa_2023)
        self.db.flush()

        self.db.add_all([
            Clause(tenant_id="tenant_inv", agreement_id=msa_2023.id, section="Section 4.1", title="Payment", topic="PAYMENT_TERMS", authority_class="governing_agreement", content="Net 45 payment.", structured_slots={"net_days": 45}, is_active=True),
            Clause(tenant_id="tenant_inv", agreement_id=msa_2023.id, section="Section 8.1", title="Liability", topic="LIMITATION_OF_LIABILITY", authority_class="governing_agreement", content="Liability capped at $1,000,000.", structured_slots={"cap_amount": 1000000.0}, is_active=True),
            Clause(tenant_id="tenant_inv", agreement_id=msa_2023.id, section="Section 3.1", title="Fees", topic="FEES", authority_class="governing_agreement", content="Standard hourly rate $120/hr.", structured_slots={"hourly_rate": 120}, is_active=True),
        ])

        rel_sup = AgreementRelation(
            tenant_id="tenant_inv",
            source_agreement_id=msa_2023.id,
            target_agreement_id=msa_2021.id,
            relation_type="SUPERSEDES",
            clause_scope="ALL",
            status="confirmed",
            effective_date=datetime(2023, 1, 15)
        )
        self.db.add(rel_sup)

        # 3. Amendment No. 1 (Net 60)
        amd_1 = Agreement(
            tenant_id="tenant_inv",
            title="Amendment No. 1 to Restated MSA",
            instrument_type="amendment",
            counterparty=cp,
            effective_date=datetime(2023, 6, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(amd_1)
        self.db.flush()

        self.db.add(Clause(tenant_id="tenant_inv", agreement_id=amd_1.id, section="Section 4.1", title="Payment", topic="PAYMENT_TERMS", authority_class="amendment", content="Section 4.1 amended: Net 60 days.", structured_slots={"net_days": 60}, is_active=True))
        self.db.add(AgreementRelation(tenant_id="tenant_inv", source_agreement_id=amd_1.id, target_agreement_id=msa_2023.id, relation_type="AMENDS", clause_scope="Section 4.1", status="confirmed", effective_date=datetime(2023, 6, 1)))

        # 4. Amendment No. 2 ($2M liability cap)
        amd_2 = Agreement(
            tenant_id="tenant_inv",
            title="Amendment No. 2 to Restated MSA",
            instrument_type="amendment",
            counterparty=cp,
            effective_date=datetime(2023, 11, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(amd_2)
        self.db.flush()

        self.db.add(Clause(tenant_id="tenant_inv", agreement_id=amd_2.id, section="Section 8.1", title="Liability", topic="LIMITATION_OF_LIABILITY", authority_class="amendment", content="Section 8.1 amended: cap raised to $2,000,000.", structured_slots={"cap_amount": 2000000.0}, is_active=True))
        self.db.add(AgreementRelation(tenant_id="tenant_inv", source_agreement_id=amd_2.id, target_agreement_id=msa_2023.id, relation_type="AMENDS", clause_scope="Section 8.1", status="confirmed", effective_date=datetime(2023, 11, 1)))

        # 5. Amendment No. 3 (Restores Net 30, 1.5% interest)
        amd_3 = Agreement(
            tenant_id="tenant_inv",
            title="Amendment No. 3 to Restated MSA",
            instrument_type="amendment",
            counterparty=cp,
            effective_date=datetime(2024, 3, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(amd_3)
        self.db.flush()

        self.db.add(Clause(tenant_id="tenant_inv", agreement_id=amd_3.id, section="Section 4.1", title="Payment", topic="PAYMENT_TERMS", authority_class="amendment", content="Payment amended: Net 30 days with 1.5% interest.", structured_slots={"net_days": 30, "late_interest_pct": 1.5}, is_active=True))
        self.db.add(AgreementRelation(tenant_id="tenant_inv", source_agreement_id=amd_3.id, target_agreement_id=amd_1.id, relation_type="AMENDS", clause_scope="Section 4.1", status="confirmed", effective_date=datetime(2024, 3, 1)))

        # 6. Schedule A-1 (Overrides fees to $150/hr)
        sch_a1 = Agreement(
            tenant_id="tenant_inv",
            title="Schedule A-1 Fee Schedule",
            instrument_type="schedule",
            counterparty=cp,
            effective_date=datetime(2024, 5, 1),
            execution_status="executed",
            status="active"
        )
        self.db.add(sch_a1)
        self.db.flush()

        self.db.add(Clause(tenant_id="tenant_inv", agreement_id=sch_a1.id, section="Schedule 1.1", title="Fee Override", topic="FEES", authority_class="statement_of_work", content="Consulting rate is $150/hr.", structured_slots={"hourly_rate": 150}, is_active=True))
        self.db.add(AgreementRelation(tenant_id="tenant_inv", source_agreement_id=sch_a1.id, target_agreement_id=msa_2023.id, relation_type="STATEMENT_OF_WORK", clause_scope="FEES", status="confirmed", effective_date=datetime(2024, 5, 1)))

        # 7. Draft Amendment No. 4 (Unexecuted draft proposing $100k cap and Net 90 payment - MUST LOSE!)
        draft_amd_4 = Agreement(
            tenant_id="tenant_inv",
            title="Draft Amendment No. 4",
            instrument_type="amendment",
            counterparty=cp,
            effective_date=datetime(2024, 7, 1),
            execution_status="draft",
            status="draft"
        )
        self.db.add(draft_amd_4)
        self.db.flush()

        self.db.add_all([
            Clause(tenant_id="tenant_inv", agreement_id=draft_amd_4.id, section="Section 4.1", title="Draft Payment", topic="PAYMENT_TERMS", authority_class="amendment", content="Draft proposes Net 90.", structured_slots={"net_days": 90}, is_active=True),
            Clause(tenant_id="tenant_inv", agreement_id=draft_amd_4.id, section="Section 8.1", title="Draft Liability", topic="LIMITATION_OF_LIABILITY", authority_class="amendment", content="Draft proposes $100,000 cap.", structured_slots={"cap_amount": 100000.0}, is_active=True),
        ])
        self.db.add(AgreementRelation(tenant_id="tenant_inv", source_agreement_id=draft_amd_4.id, target_agreement_id=msa_2023.id, relation_type="AMENDS", clause_scope="ALL", status="confirmed", effective_date=datetime(2024, 7, 1)))

        self.db.commit()

        # --- Temporal Verification Matrix ---

        # Phase 1: 2021-06-01 (Only 2021 MSA is effective)
        res_2021 = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="LIMITATION_OF_LIABILITY", as_of_date="2021-06-01")
        self.assertEqual(res_2021["controlling_clause"]["structured_slots"]["cap_amount"], 500000.0)

        # Phase 2: 2023-03-01 (2023 Restated MSA took effect, superseding 2021 MSA)
        res_2023_cap = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="LIMITATION_OF_LIABILITY", as_of_date="2023-03-01")
        self.assertEqual(res_2023_cap["controlling_clause"]["structured_slots"]["cap_amount"], 1000000.0)
        res_2023_pay = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="PAYMENT_TERMS", as_of_date="2023-03-01")
        self.assertEqual(res_2023_pay["controlling_clause"]["structured_slots"]["net_days"], 45)

        # Phase 3: 2023-07-01 (Amendment 1 in effect: Net 60)
        res_amd1 = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="PAYMENT_TERMS", as_of_date="2023-07-01")
        self.assertEqual(res_amd1["controlling_clause"]["structured_slots"]["net_days"], 60)

        # Phase 4: 2023-12-01 (Amendment 2 in effect: $2,000,000 cap)
        res_amd2 = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="LIMITATION_OF_LIABILITY", as_of_date="2023-12-01")
        self.assertEqual(res_amd2["controlling_clause"]["structured_slots"]["cap_amount"], 2000000.0)

        # Phase 5: 2024-04-01 (Amendment 3 in effect: Net 30, 1.5% interest)
        res_amd3 = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="PAYMENT_TERMS", as_of_date="2024-04-01")
        self.assertEqual(res_amd3["controlling_clause"]["structured_slots"]["net_days"], 30)
        self.assertEqual(res_amd3["controlling_clause"]["structured_slots"]["late_interest_pct"], 1.5)

        # Phase 6: 2024-08-01 (Schedule A-1 fee override + Draft Amd 4 rejection)
        # Fees: Schedule A-1 controls fees ($150/hr)
        res_fees = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="FEES", as_of_date="2024-08-01")
        self.assertEqual(res_fees["controlling_clause"]["agreement_id"], sch_a1.id)
        self.assertEqual(res_fees["controlling_clause"]["structured_slots"]["hourly_rate"], 150)

        # Liability: Draft Amd 4 ($100k) CANNOT win because it's draft! Amendment 2 ($2M) controls!
        res_final_cap = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="LIMITATION_OF_LIABILITY", as_of_date="2024-08-01")
        self.assertEqual(res_final_cap["controlling_clause"]["agreement_id"], amd_2.id)
        self.assertEqual(res_final_cap["controlling_clause"]["structured_slots"]["cap_amount"], 2000000.0)

        # Payment: Draft Amd 4 (Net 90) CANNOT win! Amendment 3 (Net 30) controls!
        res_final_pay = resolve_controlling_clause(db=self.db, tenant_id="tenant_inv", counterparty=cp, topic="PAYMENT_TERMS", as_of_date="2024-08-01")
        self.assertEqual(res_final_pay["controlling_clause"]["agreement_id"], amd_3.id)
        self.assertEqual(res_final_pay["controlling_clause"]["structured_slots"]["net_days"], 30)


if __name__ == "__main__":
    unittest.main()
