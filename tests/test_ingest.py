import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.config
import src.backend.ingest
import src.backend.rag
from src.backend.db import CommercialClauseVector, init_db
from src.backend.ingest import ingest_business_document, ingest_mock_data


class TestIngest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

        mock_vec = [0.03] * 1024
        src.backend.rag.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.rag.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))
        src.backend.ingest.get_embedding = MagicMock(return_value=mock_vec)
        src.backend.ingest.get_embeddings_batch = MagicMock(side_effect=lambda texts: [mock_vec] * len(texts))

    def test_01_ingest_mock_data_idempotency(self):
        db = self.SessionLocal()
        try:
            rep1 = ingest_mock_data(db)
            self.assertGreaterEqual(rep1["inserted"], 1)

            rep2 = ingest_mock_data(db)
            self.assertEqual(rep2["inserted"], 0)
            self.assertGreaterEqual(rep2["skipped"], 1)
        finally:
            db.close()

    def test_02_ingest_markdown_file(self):
        doc_content = (
            "# Service Level Agreement Addendum\n\n"
            "## Section 1.1 Uptime Guarantee\n"
            "Vendor guarantees 99.95% monthly uptime for all enterprise compute nodes.\n\n"
            "## Section 1.2 Maintenance Schedule\n"
            "Maintenance shall occur only during off-peak weekend windows.\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
            f.write(doc_content)
            temp_path = f.name

        temp_dir = os.path.dirname(temp_path)
        src.backend.config.settings.extra_allowed_dirs.append(temp_dir)

        db = self.SessionLocal()
        try:
            report = ingest_business_document(
                file_path=temp_path,
                deal_id=501,
                doc_type="sla",
                organization="Acme Corp",
                db=db
            )
            self.assertEqual(report["status"], "completed")
            self.assertGreaterEqual(report["chunks_out"], 2)
            self.assertGreaterEqual(report["records_inserted"], 2)

            records = db.query(CommercialClauseVector).filter(CommercialClauseVector.title == os.path.basename(temp_path)).all()
            self.assertGreaterEqual(len(records), 2)
        finally:
            db.close()
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_03_security_directory_boundary(self):
        db = self.SessionLocal()
        try:
            with self.assertRaises(ValueError):
                ingest_business_document(
                    file_path="/unauthorized/root/dir/secret_contract.pdf",
                    db=db
                )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
