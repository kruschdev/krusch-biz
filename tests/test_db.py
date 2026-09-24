import json
import os
import sys
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.db import (
    CommercialClauseVector,
    CommercialGroundingReport,
    DealEvidence,
    DealMatter,
    init_db,
)


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_deal_matter_creation_and_soft_delete(self):
        deal = DealMatter(
            deal_code="DEAL-TEST-001",
            company_name="Acme Corp",
            counterparty_name="CloudScale AI",
            deal_type="Vendor Procurement",
            title="Enterprise Cloud Agreement",
            context_facts="Negotiating liability caps and SLA terms."
        )
        self.db.add(deal)
        self.db.commit()
        self.assertIsNotNone(deal.id)
        self.assertFalse(deal.is_deleted)

        deal.is_deleted = True
        self.db.commit()

        active = self.db.query(DealMatter).filter(DealMatter.id == deal.id, DealMatter.is_deleted == False).first()
        self.assertIsNone(active)

    def test_clause_vector_creation(self):
        clause = CommercialClauseVector(
            organization="Acme Corp",
            agreement_type="Master Services Agreement",
            section="Section 10.1",
            title="Limitation of Liability",
            hierarchy_level="clause",
            authority_class="governing_agreement",
            content="Aggregate liability shall not exceed 12 months fees.",
            source_hash="testhash123"
        )
        self.db.add(clause)
        self.db.commit()
        self.assertIsNotNone(clause.id)

        fetched = self.db.query(CommercialClauseVector).filter(CommercialClauseVector.section == "Section 10.1").first()
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.organization, "Acme Corp")

    def test_deal_evidence_isolation(self):
        d1 = DealMatter(id=101, tenant_id="org_default", title="Deal 101", context_facts="Context 101")
        d2 = DealMatter(id=102, tenant_id="org_default", title="Deal 102", context_facts="Context 102")
        self.db.add_all([d1, d2])
        self.db.flush()

        ev1 = DealEvidence(
            deal_id=101,
            filename="proposal_cloudscale.pdf",
            doc_type="contract",
            page_number=1,
            section_locator="Section 1",
            content="Proposal details for deal 101"
        )
        ev2 = DealEvidence(
            deal_id=102,
            filename="confidential_memo.docx",
            doc_type="redline",
            page_number=1,
            section_locator="Section 1",
            content="Confidential terms for deal 102"
        )
        self.db.add_all([ev1, ev2])
        self.db.commit()

        deal101_evidence = self.db.query(DealEvidence).filter(DealEvidence.deal_id == 101).all()
        self.assertEqual(len(deal101_evidence), 1)
        self.assertEqual(deal101_evidence[0].filename, "proposal_cloudscale.pdf")

    def test_grounding_report_persistence(self):
        report = CommercialGroundingReport(
            deal_id=101,
            total_claims=5,
            supported_claims=5,
            unsupported_claims=0,
            invented_clauses=0,
            superseded_terms=0,
            pass_rate=100.0,
            claims_json=json.dumps([{"claim_id": "c1", "status": "verified_grounded"}]),
            advisory_markdown="All verified."
        )
        self.db.add(report)
        self.db.commit()
        self.assertIsNotNone(report.id)

    def test_audit_log_immutability(self):
        """Verify AuditLog records are append-only and physically reject UPDATE and DELETE."""
        from src.backend.db import AuditLog
        audit = AuditLog(
            tenant_id="org_default",
            action="consult",
            actor_key_hash="hash123",
            client_ip="127.0.0.1",
            deal_id=101
        )
        self.db.add(audit)
        self.db.commit()
        audit_id = audit.id
        self.assertIsNotNone(audit_id)

        # Attempt UPDATE
        audit.action = "tampered_action"
        with self.assertRaises(PermissionError) as ctx_upd:
            self.db.commit()
        self.assertIn("strictly immutable", str(ctx_upd.exception))
        self.db.rollback()

        # Attempt DELETE
        fetched = self.db.query(AuditLog).filter(AuditLog.id == audit_id).first()
        self.db.delete(fetched)
        with self.assertRaises(PermissionError) as ctx_del:
            self.db.commit()
        self.assertIn("strictly immutable", str(ctx_del.exception))
        self.db.rollback()

    def test_purge_deal_matter_transactional_counts(self):
        """Verify purge_deal_matter_transactional atomically removes deal, evidence, reports, and invoices."""
        from src.backend.db import purge_deal_matter_transactional, Invoice
        deal = DealMatter(id=201, tenant_id="org_default", title="Deal Purge Test", context_facts="Facts")
        self.db.add(deal)
        self.db.flush()

        ev1 = DealEvidence(deal_id=201, tenant_id="org_default", filename="f1.pdf", content="c1")
        ev2 = DealEvidence(deal_id=201, tenant_id="org_default", filename="f2.pdf", content="c2")
        rep = CommercialGroundingReport(deal_id=201, tenant_id="org_default", claims_json="[]")
        inv = Invoice(deal_id=201, tenant_id="org_default", invoice_number="INV-201", client_name="Client")
        self.db.add_all([ev1, ev2, rep, inv])
        self.db.commit()

        # Pre-counts
        self.assertEqual(self.db.query(DealMatter).filter(DealMatter.id == 201).count(), 1)
        self.assertEqual(self.db.query(DealEvidence).filter(DealEvidence.deal_id == 201).count(), 2)
        self.assertEqual(self.db.query(CommercialGroundingReport).filter(CommercialGroundingReport.deal_id == 201).count(), 1)
        self.assertEqual(self.db.query(Invoice).filter(Invoice.deal_id == 201).count(), 1)

        result = purge_deal_matter_transactional(self.db, "org_default", 201)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["evidence"], 2)
        self.assertEqual(result["reports"], 1)
        self.assertEqual(result["invoices"], 1)

        # Post-counts
        self.assertEqual(self.db.query(DealMatter).filter(DealMatter.id == 201).count(), 0)
        self.assertEqual(self.db.query(DealEvidence).filter(DealEvidence.deal_id == 201).count(), 0)
        self.assertEqual(self.db.query(CommercialGroundingReport).filter(CommercialGroundingReport.deal_id == 201).count(), 0)
        self.assertEqual(self.db.query(Invoice).filter(Invoice.deal_id == 201).count(), 0)

    def test_purge_agreement_transactional_counts(self):
        """Verify purge_agreement_transactional atomically removes agreement, portfolio, relations, clauses, and vectors."""
        from src.backend.db import (
            Agreement, Clause, AgreementRelation, ContractPortfolio,
            purge_agreement_transactional, write_clause_and_vector_transactional
        )
        ag = Agreement(
            id=301,
            tenant_id="org_default",
            title="Purge Test MSA",
            instrument_type="master_services_agreement",
            raw_hash="raw_hash_301"
        )
        self.db.add(ag)
        self.db.flush()

        pf = ContractPortfolio(
            agreement_id=301,
            tenant_id="org_default",
            contract_name="Purge Test MSA",
            vendor="Acme"
        )
        self.db.add(pf)

        target_ag = Agreement(
            id=302,
            tenant_id="org_default",
            title="Target MSA",
            instrument_type="master_services_agreement",
            raw_hash="raw_hash_302"
        )
        self.db.add(target_ag)
        self.db.flush()

        rel = AgreementRelation(
            tenant_id="org_default",
            source_agreement_id=301,
            target_agreement_id=302,
            relation_type="AMENDS"
        )
        self.db.add(rel)

        cl, vec = write_clause_and_vector_transactional(
            self.db,
            clause_kwargs={
                "tenant_id": "org_default",
                "agreement_id": 301,
                "section": "Section 1.1",
                "title": "Purge Test Clause",
                "content": "Purge content"
            },
            vector_kwargs={
                "tenant_id": "org_default",
                "organization": "Acme",
                "agreement_type": "master_services_agreement",
                "title": "Purge Test MSA",
                "section": "Section 1.1",
                "content": "Purge content"
            }
        )
        self.db.commit()

        # Pre-counts
        self.assertEqual(self.db.query(Agreement).filter(Agreement.id == 301).count(), 1)
        self.assertEqual(self.db.query(ContractPortfolio).filter(ContractPortfolio.agreement_id == 301).count(), 1)
        self.assertEqual(self.db.query(AgreementRelation).filter(AgreementRelation.source_agreement_id == 301).count(), 1)
        self.assertEqual(self.db.query(Clause).filter(Clause.agreement_id == 301).count(), 1)
        self.assertEqual(self.db.query(CommercialClauseVector).filter(CommercialClauseVector.title == "Purge Test MSA").count(), 1)

        result = purge_agreement_transactional(self.db, "org_default", 301)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["portfolio"], 1)
        self.assertEqual(result["relations"], 1)
        self.assertEqual(result["clauses"], 1)
        self.assertEqual(result["vectors"], 1)

        # Post-counts
        self.assertEqual(self.db.query(Agreement).filter(Agreement.id == 301).count(), 0)
        self.assertEqual(self.db.query(ContractPortfolio).filter(ContractPortfolio.agreement_id == 301).count(), 0)
        self.assertEqual(self.db.query(AgreementRelation).filter(AgreementRelation.source_agreement_id == 301).count(), 0)
        self.assertEqual(self.db.query(Clause).filter(Clause.agreement_id == 301).count(), 0)
        self.assertEqual(self.db.query(CommercialClauseVector).filter(CommercialClauseVector.title == "Purge Test MSA").count(), 0)


if __name__ == "__main__":
    unittest.main()

