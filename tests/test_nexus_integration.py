"""
tests/test_nexus_integration.py
===============================
Cross-repository integration test suite verifying that KruschBiz integrates cleanly
with KruschNexus as its sovereign document ingestion spine and citation engine.

Tests:
1. Ingesting markdown contracts with section-aware headers.
2. Ingesting real DOCX contract/policy fixtures from KruschNexus.
3. Ingesting real PDF contract fixtures from KruschNexus with page-true citations.
4. Multipart file upload via POST /api/ingest/upload.
5. Hybrid retrieval and citation verification of ingested chunks.
6. Deal room evidence isolation.
"""

import io
import os
import sys
import tempfile
import unittest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OLLAMA_EMBED_HOST"] = "http://mock-ollama:11434"
os.environ["OLLAMA_BASE_URL"] = "http://mock-ollama:11434"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

NEXUS_DIR = os.getenv("KRUSCH_NEXUS_DIR")
if not NEXUS_DIR:
    candidates = [
        "/home/krusch/homelab/projects/krusch-nexus",
        os.path.join(PROJECT_ROOT, "krusch-nexus"),
        os.path.join(os.path.dirname(PROJECT_ROOT), "krusch-nexus"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            NEXUS_DIR = c
            break

if NEXUS_DIR:
    NEXUS_SRC = os.path.join(NEXUS_DIR, "src")
    FIXTURES_DIR = os.path.join(NEXUS_DIR, "tests", "fixtures")
    if NEXUS_SRC not in sys.path and os.path.isdir(NEXUS_SRC):
        sys.path.insert(0, NEXUS_SRC)
else:
    NEXUS_SRC = os.getenv("KRUSCH_NEXUS_PATH")
    if NEXUS_SRC and NEXUS_SRC not in sys.path and os.path.isdir(NEXUS_SRC):
        sys.path.insert(0, NEXUS_SRC)
    FIXTURES_DIR = None

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.config
import src.backend.db
import src.backend.ingest
import src.backend.main
import src.backend.rag
from src.backend.db import CommercialClauseVector, DealEvidence, init_db
from src.backend.ingest import ingest_business_document
from src.backend.main import app, get_db


class TestNexusIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import krusch_nexus
        except ImportError:
            raise unittest.SkipTest("krusch_nexus is not available in the current environment")

        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        src.backend.db.SessionLocal = cls.TestingSessionLocal
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        def mock_embed(text: str) -> list[float]:
            import hashlib
            h = hashlib.md5(text.encode("utf-8")).digest()
            val = (h[0] / 255.0) * 0.1
            vec = [0.01] * 1024
            vec[0] = val
            return vec

        def mock_embed_batch(texts: list[str]) -> list[list[float]]:
            return [mock_embed(t) for t in texts]

        src.backend.rag.get_embedding = mock_embed
        src.backend.rag.get_embeddings_batch = mock_embed_batch
        src.backend.ingest.get_embedding = mock_embed
        src.backend.ingest.get_embeddings_batch = mock_embed_batch
        src.backend.main.get_embedding = mock_embed

    def test_01_ingest_markdown_contract(self):
        """Verify markdown contract ingestion extracts section-aware chunks with headers."""
        doc_content = (
            "# Master Subscription Agreement\n\n"
            "## Section 4.1 Payment Terms\n"
            "Customer shall pay all undisputed invoice amounts within thirty (30) days of receipt.\n\n"
            "## Section 4.2 Late Penalties\n"
            "Overdue payments shall accrue interest at 1.5% per month.\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
            f.write(doc_content)
            temp_path = f.name

        temp_dir = os.path.dirname(temp_path)
        src.backend.config.settings.extra_allowed_dirs.append(temp_dir)

        try:
            db = self.TestingSessionLocal()
            report = ingest_business_document(
                file_path=temp_path,
                deal_id=301,
                doc_type="contract",
                organization="Acme Corp",
                db=db
            )
            self.assertEqual(report["status"], "completed")
            self.assertEqual(report["pages_in"], 1)
            self.assertGreaterEqual(report["chunks_out"], 2)
            self.assertGreaterEqual(report["records_inserted"], 2)

            # Check database records
            records = db.query(CommercialClauseVector).filter(CommercialClauseVector.title == os.path.basename(temp_path)).all()
            self.assertGreaterEqual(len(records), 2)
            headers = [r.source_header for r in records]
            self.assertTrue(any("Section 4.1" in h for h in headers))
            self.assertTrue(any("Section 4.2" in h for h in headers))

            # Check deal evidence isolation
            ev_records = db.query(DealEvidence).filter(DealEvidence.deal_id == 301).all()
            self.assertGreaterEqual(len(ev_records), 2)
            db.close()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_02_ingest_docx_policy_fixture(self):
        """Verify ingestion of real DOCX fixture from KruschNexus."""
        if not FIXTURES_DIR or not os.path.exists(FIXTURES_DIR):
            self.skipTest("KruschNexus fixtures directory not available")
        docx_path = os.path.join(FIXTURES_DIR, "policy_manual.docx")
        if not os.path.exists(docx_path):
            self.skipTest(f"Fixture {docx_path} not found")

        src.backend.config.settings.extra_allowed_dirs.append(FIXTURES_DIR)
        db = self.TestingSessionLocal()
        try:
            report = ingest_business_document(
                file_path=docx_path,
                deal_id=302,
                doc_type="policy",
                organization="Acme Corp",
                db=db
            )
            self.assertEqual(report["status"], "completed")
            self.assertGreaterEqual(report["pages_in"], 1)
            self.assertGreaterEqual(report["chunks_out"], 1)

            records = db.query(CommercialClauseVector).filter(CommercialClauseVector.title == "policy_manual.docx").all()
            self.assertGreaterEqual(len(records), 1)
        finally:
            db.close()

    def test_03_ingest_pdf_contract_fixture(self):
        """Verify ingestion of real PDF fixture with page tracking from KruschNexus."""
        if not FIXTURES_DIR or not os.path.exists(FIXTURES_DIR):
            self.skipTest("KruschNexus fixtures directory not available")
        pdf_path = os.path.join(FIXTURES_DIR, "sample_contract.pdf")
        if not os.path.exists(pdf_path):
            self.skipTest(f"Fixture {pdf_path} not found")

        src.backend.config.settings.extra_allowed_dirs.append(FIXTURES_DIR)
        db = self.TestingSessionLocal()
        try:
            report = ingest_business_document(
                file_path=pdf_path,
                deal_id=303,
                doc_type="contract",
                organization="Acme Corp",
                db=db
            )
            self.assertEqual(report["status"], "completed")
            self.assertGreaterEqual(report["pages_in"], 1)
            self.assertGreaterEqual(report["chunks_out"], 1)

            records = db.query(CommercialClauseVector).filter(CommercialClauseVector.title == "sample_contract.pdf").all()
            self.assertGreaterEqual(len(records), 1)
            self.assertIn("p.", records[0].section)
        finally:
            db.close()

    def test_04_multipart_upload_endpoint(self):
        """Verify file upload via POST /api/ingest/upload."""
        file_content = (
            b"# Data Processing Agreement\n\n"
            b"## Section 3.4 Breach Notification\n"
            b"Vendor shall notify Customer within twenty-four (24) hours of a confirmed security incident.\n"
        )

        resp = self.client.post(
            "/api/ingest/upload",
            files={"file": ("dpa_upload.md", io.BytesIO(file_content), "text/markdown")},
            data={"deal_id": 304, "doc_type": "contract"}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["filename"], "dpa_upload.md")
        self.assertEqual(data["deal_id"], 304)

        # Verify search retrieves the uploaded clause
        search_resp = self.client.get("/api/clauses?q=twenty-four+hours+security+incident")
        self.assertEqual(search_resp.status_code, 200)
        hits = search_resp.json()
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("twenty-four", hits[0]["content"])


if __name__ == "__main__":
    unittest.main()
