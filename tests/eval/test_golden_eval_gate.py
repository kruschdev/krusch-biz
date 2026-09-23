import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OLLAMA_EMBED_HOST"] = "http://mock-ollama:11434"
os.environ["OLLAMA_BASE_URL"] = "http://mock-ollama:11434"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db
import src.backend.ingest
import src.backend.rag
from scripts.eval_retrieval_and_grounding import run_golden_evaluation
from src.backend.db import init_db
from src.backend.ingest import ingest_mock_data


class TestGoldenBusinessEvalGate(unittest.TestCase):
    """
    CI Gate: Ensures retrieval recall and assertion grounding pass rates
    meet minimum sovereign corporate standards on the frozen golden benchmark.
    """
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
        src.backend.rag.SessionLocal = cls.Session
        src.backend.ingest.SessionLocal = cls.Session

        init_db(cls.engine)

        mock_vec = [0.05] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))

        db = cls.Session()
        ingest_mock_data(db)
        db.close()

    def test_golden_eval_metrics_ci_gate(self):
        eval_path = os.path.join(PROJECT_ROOT, "data", "eval", "golden_business_eval.json")
        session = self.Session()
        try:
            metrics = run_golden_evaluation(dataset_path=eval_path, db_session=session)

            # Assert minimum acceptable recall on frozen gold standards (>= 90%)
            self.assertGreaterEqual(
                metrics["recall_at_5"], 90.0,
                f"Recall@5 ({metrics['recall_at_5']}%) regressed below 90% threshold on golden benchmark."
            )

            # Assert no distractor / superseded agreements leaked through
            self.assertEqual(
                metrics["distractor_leaks"], 0,
                f"Detected {metrics['distractor_leaks']} forbidden distractor / superseded agreement leaks."
            )

            # Assert assertion grounding pass rate (>= 90%)
            self.assertGreaterEqual(
                metrics["grounding_pass_rate"], 90.0,
                f"Assertion grounding pass rate ({metrics['grounding_pass_rate']}%) regressed below 90% threshold."
            )

            # Assert Mean Reciprocal Rank (MRR >= 0.85)
            self.assertGreaterEqual(
                metrics["mrr"], 0.85,
                f"MRR ({metrics['mrr']}) regressed below 0.85 threshold."
            )

        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
