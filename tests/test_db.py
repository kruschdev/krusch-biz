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


if __name__ == "__main__":
    unittest.main()
