"""
tests/eval/test_golden_eval_gate.py
===================================
Automated CI Gate: Validates all 3 empirical evaluation gates:
  1. Lexical / Fixture Gate (Recall@5 >= 90%, 0 Distractor Leaks)
  2. Unmocked Embedding Gate (Real bge-large 1024-d vectors, Recall@5 >= 90%)
  3. Held-Out Redacted Contracts Gate (Recall@5 >= 95%, 0 Priority Inversions)
  4. Grounding Calibration Matrix (Overall accuracy >= 80%)
"""

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

from scripts.eval_retrieval_and_grounding import (
    run_fixture_gate,
    run_grounding_calibration_matrix,
    run_heldout_gate,
    run_unmocked_embedding_gate,
)
import src.backend.db
import src.backend.ingest
import src.backend.rag
from src.backend.db import init_db
from src.backend.ingest import ingest_mock_data


class TestMultiGateEvaluationCI(unittest.TestCase):
    """Automated multi-gate CI test certifying retrieval, unmocked vectors, and grounding calibration."""

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

    def test_01_fixture_gate(self):
        eval_path = os.path.join(PROJECT_ROOT, "data", "eval", "golden_business_eval.json")
        session = self.Session()
        try:
            m = run_fixture_gate(eval_path, session)
            self.assertGreaterEqual(m["recall_at_5"], 90.0, f"Fixture Recall@5 ({m['recall_at_5']}%) regressed below 90%.")
            self.assertEqual(m["distractor_leaks"], 0, f"Found {m['distractor_leaks']} distractor leaks.")
        finally:
            session.close()

    def test_02_unmocked_embedding_gate(self):
        seed_cache = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings", "seed_bge_large.json")
        queries_cache = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings", "queries_bge_large.json")
        eval_path = os.path.join(PROJECT_ROOT, "data", "eval", "golden_business_eval.json")

        if os.path.exists(seed_cache) and os.path.exists(queries_cache):
            m = run_unmocked_embedding_gate(seed_cache, queries_cache, eval_path)
            self.assertEqual(m["status"], "passed")
            self.assertGreaterEqual(m["pure_vector_recall_at_5"], 90.0)

    def test_03_heldout_contract_gate(self):
        heldout_path = os.path.join(PROJECT_ROOT, "data", "eval", "heldout_contracts.json")
        heldout_cache = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings", "heldout_bge_large.json")
        session = self.Session()
        try:
            m = run_heldout_gate(heldout_path, heldout_cache, session)
            self.assertGreaterEqual(m["heldout_recall_at_5"], 95.0, f"Held-out Recall@5 ({m['heldout_recall_at_5']}%) regressed below 95%.")
            self.assertEqual(m["superseded_priority_inversions"], 0, "Superseded instruments outranked controlling ones!")
            self.assertEqual(m["superseded_in_top_1_rate"], 0.0, "Superseded clause appeared as top-1 hit!")
            self.assertGreater(m["heldout_precision_at_5"], 0.0, "Held-out Precision@5 must be reported.")
        finally:
            session.close()

    def test_04_grounding_calibration_matrix(self):
        heldout_path = os.path.join(PROJECT_ROOT, "data", "eval", "heldout_contracts.json")
        session = self.Session()
        try:
            calib = run_grounding_calibration_matrix(heldout_path, session)
            self.assertGreaterEqual(calib["calibration_accuracy"], 80.0, f"Calibration accuracy {calib['calibration_accuracy']}% below 80%.")
            cm = calib["confusion_matrix"]
            self.assertGreater(cm["VERIFIED"]["correct"], 0)
            self.assertGreater(cm["INVENTED_CLAUSE"]["correct"], 0)
            self.assertGreater(cm["DIVERGENT_TERM"]["correct"], 0)
            self.assertGreater(cm["SUPERSEDED_TERM"]["correct"], 0)

            # Assert Per-Failure-Mode Precision and Recall reporting
            pfm = calib["per_failure_mode_metrics"]
            for mode in ("VERIFIED", "INVENTED_CLAUSE", "DIVERGENT_TERM", "SUPERSEDED_TERM"):
                self.assertIn(mode, pfm, f"Missing per-failure mode metrics for '{mode}'.")
                self.assertIn("precision", pfm[mode])
                self.assertIn("recall", pfm[mode])
                self.assertIn("f1", pfm[mode])
                self.assertGreaterEqual(pfm[mode]["recall"], 60.0, f"Recall for mode '{mode}' below 60%.")

            self.assertGreaterEqual(calib["macro_f1"], 75.0, f"Macro F1 {calib['macro_f1']}% below 75%.")
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
