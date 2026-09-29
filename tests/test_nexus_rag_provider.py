"""
tests/test_nexus_rag_provider.py
================================
Unit tests verifying that KruschBiz can hook into KruschNexus and Wondersearch
as a swappable RAG retrieval provider while preserving air-gap security invariants.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

NEXUS_SRC = os.path.join(os.path.dirname(PROJECT_ROOT), "krusch-nexus", "src")
if os.path.isdir(NEXUS_SRC) and NEXUS_SRC not in sys.path:
    sys.path.insert(0, NEXUS_SRC)

try:
    from krusch_nexus.models import SearchHit
    from krusch_nexus.exceptions import AirGapViolationError
    HAS_NEXUS = True
except ImportError:
    HAS_NEXUS = False
    SearchHit = None
    AirGapViolationError = Exception

from src.backend.config import settings
from src.backend.nexus_rag import (
    is_nexus_available,
    get_nexus_client,
    search_clauses_nexus,
    search_deal_evidence_nexus
)
from src.backend.rag import retrieve_clauses, retrieve_deal_evidence


class TestBizNexusRagProvider(unittest.TestCase):
    """Test suite for KruschBiz RAG delegation to Nexus/Wondersearch."""

    @classmethod
    def setUpClass(cls):
        if not HAS_NEXUS:
            raise unittest.SkipTest("krusch_nexus is not available in the current environment")

    def setUp(self):
        self.orig_rag_provider = getattr(settings, "RAG_PROVIDER", "local")
        self.orig_allow_cloud = getattr(settings, "ALLOW_CLOUD", False)

    def tearDown(self):
        settings.RAG_PROVIDER = self.orig_rag_provider
        settings.ALLOW_CLOUD = self.orig_allow_cloud
        import src.backend.nexus_rag
        src.backend.nexus_rag._NEXUS_CLIENT = None

    def test_nexus_available(self):
        """KruschNexus should be discoverable in the monorepo."""
        self.assertTrue(is_nexus_available())

    def test_air_gap_protection_wondersearch_blocked_by_default(self):
        """Wondersearch backend must raise AirGapViolationError when ALLOW_CLOUD is not 1."""
        settings.ALLOW_CLOUD = False
        with patch.dict(os.environ, {"NEXUS_BACKEND": "wondersearch", "ALLOW_CLOUD": "0"}):
            with self.assertRaises(AirGapViolationError):
                get_nexus_client()

    def test_wondersearch_allowed_when_allow_cloud_enabled(self):
        """Wondersearch backend succeeds when ALLOW_CLOUD=1."""
        settings.ALLOW_CLOUD = True
        with patch.dict(os.environ, {
            "NEXUS_BACKEND": "wondersearch",
            "ALLOW_CLOUD": "1",
            "WONDERSEARCH_API_KEY": "ws_test_key"
        }):
            client = get_nexus_client()
            self.assertIsNotNone(client)
            self.assertEqual(client.config.backend, "wondersearch")

    @patch("src.backend.nexus_rag.get_nexus_client")
    def test_retrieve_clauses_routing(self, mock_get_client):
        """When RAG_PROVIDER='nexus', retrieve_clauses delegates to NexusClient and preserves INV-11 coordinates."""
        settings.RAG_PROVIDER = "nexus"

        mock_hit = SearchHit(
            chunk_id=501,
            document_id=12,
            text="Section 4.1: Undisputed invoices payable within 30 days.",
            score=0.95,
            citation="Master Services Agreement, p. 4",
            locator="Section 4.1",
            page_number=4,
            char_start=200,
            char_end=280,
            bbox=[72.0, 180.0, 500.0, 210.0],
            score_vector={
                "organization": "Acme Corp",
                "agreement_type": "Master Services Agreement",
                "domain": "Procurement & Invoicing",
                "topic": "Payment Terms & Invoicing Due Date",
                "structured_slots": {"payment_deadline_days": 30}
            }
        )

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_hit]
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        results = retrieve_clauses(db=mock_db, query="payment deadline Net 30")
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["id"], 501)
        self.assertEqual(r["organization"], "Acme Corp")
        self.assertEqual(r["section"], "Section 4.1")
        self.assertEqual(r["page_number"], 4)
        self.assertEqual(r["bbox"], [72.0, 180.0, 500.0, 210.0])
        self.assertEqual(r["char_start"], 200)
        self.assertEqual(r["char_end"], 280)
        self.assertEqual(r["score"], 0.95)

    @patch("src.backend.nexus_rag.get_nexus_client")
    def test_retrieve_deal_evidence_routing(self, mock_get_client):
        """When RAG_PROVIDER='nexus', retrieve_deal_evidence delegates to NexusClient with deal workspace isolation."""
        settings.RAG_PROVIDER = "nexus"

        mock_hit = SearchHit(
            chunk_id=602,
            document_id=15,
            text="Redline proposal includes 12-month trailing liability cap.",
            score=0.89,
            citation="Vendor Redline v2, p. 2",
            filename="vendor_proposal.pdf",
            locator="Section 10",
            page_number=2,
            char_start=15,
            char_end=95,
            bbox=[60.0, 200.0, 480.0, 240.0],
            doc_type="redline",
            score_vector={
                "tags": ["liability", "cap", "redline"]
            }
        )

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_hit]
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        results = retrieve_deal_evidence(db=mock_db, deal_id=77, text_query="liability cap")
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["id"], 602)
        self.assertEqual(r["deal_id"], 77)
        self.assertEqual(r["filename"], "vendor_proposal.pdf")
        self.assertEqual(r["page_number"], 2)
        self.assertEqual(r["bbox"], [60.0, 200.0, 480.0, 240.0])
        mock_client.search.assert_called_once()
        self.assertEqual(mock_client.search.call_args.kwargs["workspace"], "deal_77")


if __name__ == "__main__":
    unittest.main()
