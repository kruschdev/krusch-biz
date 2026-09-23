import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.ingest
import src.backend.rag
from src.backend.db import init_db
from src.backend.ingest import ingest_mock_data
from src.backend.rag import (
    EmbeddingCache,
    expand_commercial_query,
    generate_executive_brief,
    retrieve_clauses,
    verify_commercial_grounding,
)


class TestRAG(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

        mock_vec = [0.02] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))

        db = cls.SessionLocal()
        ingest_mock_data(db)
        db.close()

    def test_01_expand_commercial_query(self):
        query = "Vendor sent an invoice with Net 30 payment terms and 1.5% late interest."
        expanded, spotted = expand_commercial_query(query)
        self.assertTrue(len(spotted) >= 1)
        self.assertIn("Payment Terms", spotted[0]["issue"])
        self.assertIn("Section 4.1", expanded)

    def test_02_embedding_cache_lru(self):
        cache = EmbeddingCache(maxsize=3)
        cache.set("modelA", "text1", [0.1, 0.2])
        cache.set("modelA", "text2", [0.3, 0.4])
        cache.set("modelA", "text3", [0.5, 0.6])

        self.assertIsNotNone(cache.get("modelA", "text1"))
        cache.set("modelA", "text4", [0.7, 0.8])
        # text2 should be evicted because text1 was recently accessed
        self.assertIsNone(cache.get("modelA", "text2"))
        self.assertIsNotNone(cache.get("modelA", "text1"))
        self.assertIsNotNone(cache.get("modelA", "text4"))

    def test_03_retrieve_clauses_hybrid(self):
        db = self.SessionLocal()
        try:
            results = retrieve_clauses(db=db, query="limitation of liability gross negligence", limit=3)
            self.assertTrue(len(results) >= 1)
            sections = [r.get("section") for r in results]
            self.assertTrue(any("10.1" in s or "10.2" in s for s in sections))
        finally:
            db.close()

    def test_04_grounding_verified(self):
        clauses = [
            {
                "section": "Section 4.1",
                "title": "Payment Terms",
                "content": "Customer shall pay all undisputed invoice amounts within thirty (30) days of the invoice date ('Net 30').",
                "superseded": False,
                "terminated": False
            }
        ]
        draft = "Pursuant to Section 4.1, Customer shall pay all undisputed invoice amounts within thirty (30) days of the invoice date."
        is_grounded, claims, md, stats = verify_commercial_grounding(draft, clauses)
        self.assertTrue(is_grounded)
        self.assertEqual(stats["pass_rate"], 100.0)
        self.assertEqual(stats["invented_clauses"], 0)

    def test_05_grounding_invented_clause(self):
        clauses = [
            {
                "section": "Section 4.1",
                "title": "Payment Terms",
                "content": "Net 30 payment required.",
                "superseded": False,
                "terminated": False
            }
        ]
        draft = "Under Section 99.9, Vendor must supply free hardware replacements."
        is_grounded, claims, md, stats = verify_commercial_grounding(draft, clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["invented_clauses"], 1)

    def test_06_grounding_superseded_agreement(self):
        clauses = [
            {
                "section": "Section 2021-MSA-4.1",
                "title": "Old Expired Payment Terms",
                "content": "Net 90 with no interest.",
                "superseded": True,
                "terminated": True,
                "superseded_by": "2025 MSA Section 4.1"
            }
        ]
        draft = "Under Section 2021-MSA-4.1, payment is due in 90 days."
        is_grounded, claims, md, stats = verify_commercial_grounding(draft, clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["superseded_terms"], 1)

    def test_07_generate_brief_refusal_when_no_authorities(self):
        refusal, stats, claims = generate_executive_brief(
            deal_title="Unknown Deal",
            context_facts="Some obscure transaction without agreements.",
            clauses=[]
        )
        self.assertIn("CANNOT_DRAFT_WITHOUT_AUTHORITIES", refusal)
        self.assertEqual(stats["pass_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
