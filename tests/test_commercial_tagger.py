import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.tagger import (
    heuristic_tag_commercial_chunk,
    sanitize_tag,
    tag_commercial_chunk,
    tag_commercial_chunk_with_llm,
)


class TestCommercialTagger(unittest.TestCase):
    def test_01_sanitize_tag(self):
        self.assertEqual(sanitize_tag("Payment Terms"), "payment-terms")
        self.assertEqual(sanitize_tag("NET_30!"), "net-30")
        self.assertEqual(sanitize_tag("   --late--interest--   "), "late-interest")
        self.assertEqual(sanitize_tag("SLA_99.9%"), "sla-999")

    def test_02_heuristic_payment_terms(self):
        content = (
            "Section 4.1 Payment Terms: Customer shall pay all undisputed invoice amounts within thirty (30) days "
            "of the invoice date ('Net 30'). Undisputed charges not received within fifteen (15) days shall accrue "
            "late interest at the rate of 1.5% per month."
        )
        res = heuristic_tag_commercial_chunk(content, filename="msa.pdf", locator="Section 4.1", doc_type="contract")
        self.assertEqual(res["topic"], "PAYMENT_TERMS")
        self.assertIn("net-30", res["tags"])
        self.assertIn("payment-terms", res["tags"])
        self.assertTrue(len(res["summary"]) > 0)
        self.assertTrue(len(res["summary"]) <= 140)

    def test_03_heuristic_limitation_of_liability(self):
        content = (
            "Section 10.1 Limitation of Liability: Except for obligations under Section 10.2, each party's maximum "
            "aggregate liability shall be limited to fees paid in the twelve (12) months preceding the incident. "
            "Neither party shall be liable for indirect or consequential damages. Carve-outs apply to gross negligence "
            "and willful misconduct."
        )
        res = heuristic_tag_commercial_chunk(content, filename="msa.pdf", locator="Section 10.1")
        self.assertEqual(res["topic"], "LIMITATION_OF_LIABILITY")
        self.assertIn("limitation-of-liability", res["tags"])
        self.assertTrue(any("gross-negligence" in t or "liability-cap" in t for t in res["tags"]))

    def test_04_heuristic_sla_performance(self):
        content = (
            "Exhibit B Section 2.1 Availability: CloudScale commits to maintaining a Monthly Uptime Percentage of at least "
            "99.9% availability during each billing cycle. If uptime falls below 95.0%, customer receives a 50% credit."
        )
        res = heuristic_tag_commercial_chunk(content, filename="sla_exhibit.pdf", locator="Exhibit B Section 2.1")
        self.assertEqual(res["topic"], "SLA_PERFORMANCE")
        self.assertTrue(any("uptime" in t or "availability" in t for t in res["tags"]))

    def test_05_heuristic_data_protection(self):
        content = (
            "Exhibit C Section 4.2 Security Breach: In the event of a confirmed security incident or personal data breach, "
            "Vendor shall notify Customer within twenty-four (24) hours of becoming aware of the incident under GDPR and CCPA."
        )
        res = heuristic_tag_commercial_chunk(content, filename="dpa.pdf", locator="Exhibit C Section 4.2")
        self.assertEqual(res["topic"], "DATA_PROTECTION")
        self.assertIn("data-protection", res["tags"])
        self.assertTrue(any("notice-24h" in t or "security-incident" in t for t in res["tags"]))

    def test_06_llm_tagger_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": '{"summary": "Customer pays Net 30 with 1.5% late fee.", "tags": ["payment-terms", "net-30", "late-fee"], "topic": "PAYMENT_TERMS"}'
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            res = tag_commercial_chunk_with_llm("Payment due in 30 days.", filename="terms.pdf")
            self.assertIsNotNone(res)
            self.assertEqual(res["topic"], "PAYMENT_TERMS")
            self.assertEqual(res["summary"], "Customer pays Net 30 with 1.5% late fee.")
            self.assertIn("net-30", res["tags"])

    def test_07_llm_tagger_fallback_on_network_error(self):
        with patch("httpx.Client.post", side_effect=Exception("Connection refused")):
            res = tag_commercial_chunk("Customer shall pay all invoices within Net 45 days.", filename="agreement.pdf", use_llm=True)
            self.assertIsNotNone(res)
            self.assertEqual(res["topic"], "PAYMENT_TERMS")
            self.assertIn("net-45", res["tags"])

    def test_08_llm_tagger_markdown_code_fences(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": '```json\n{"summary": "Mutual indemnification for third-party claims.", "tags": ["indemnification", "third-party", "defense"], "topic": "INDEMNIFICATION"}\n```'
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            res = tag_commercial_chunk_with_llm("Vendor shall defend and indemnify Customer.", filename="indemnity.pdf")
            self.assertIsNotNone(res)
            self.assertEqual(res["topic"], "INDEMNIFICATION")
            self.assertIn("indemnification", res["tags"])


    def test_09_ensemble_tagging_merges_slots_and_llm(self):
        content = "Section 4.1 Payment Terms: Invoices shall be paid within thirty (30) days ('Net 30')."
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": '{"summary": "Invoices must be satisfied within thirty days of issue.", "tags": ["corporate-finance", "accounts-payable"], "topic": "PAYMENT_TERMS"}'
        }

        with patch("httpx.Client.post", return_value=mock_resp):
            res = tag_commercial_chunk(content, filename="msa.pdf", locator="Section 4.1", use_llm=True)
            self.assertEqual(res["topic"], "PAYMENT_TERMS")
            self.assertEqual(res["summary"], "Invoices must be satisfied within thirty days of issue.")
            # Both deterministic slot tag AND LLM semantic tags should be present!
            self.assertIn("net-30", res["tags"])
            self.assertIn("corporate-finance", res["tags"])
            self.assertIn("accounts-payable", res["tags"])

    def test_10_llm_tagger_json_repair_and_allowlist(self):
        """Verify 1-pass JSON repair handles trailing commas and filters tags to allowlist + 1 free tag."""
        # Trailing comma before closing brace
        malformed_json = '{"summary": "Annual audit rights.", "tags": ["audit-rights", "inspection", "invented-custom-tag", "another-custom-tag"], "topic": "AUDIT_RIGHTS",}'
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": malformed_json}

        with patch("httpx.Client.post", return_value=mock_resp):
            res = tag_commercial_chunk_with_llm("Customer may audit books once per year.", filename="audit.pdf")
            self.assertIsNotNone(res)
            self.assertEqual(res["topic"], "AUDIT_RIGHTS")
            self.assertIn("audit-rights", res["tags"])
            self.assertIn("inspection", res["tags"])
            # At most 1 free non-allowlist tag permitted
            self.assertIn("invented-custom-tag", res["tags"])
            self.assertNotIn("another-custom-tag", res["tags"])

    def test_11_llm_tagger_cache(self):
        """Verify tagger caches responses and returns without network calls on cache hit."""
        from src.backend.tagger import tagger_cache
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "response": '{"summary": "Governing law of New York.", "tags": ["governing-law", "jurisdiction"], "topic": "GOVERNING_LAW"}'
        }

        with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
            # First call
            res1 = tag_commercial_chunk_with_llm("Governing law shall be the State of New York.", filename="gov.pdf")
            self.assertIsNotNone(res1)
            self.assertEqual(mock_post.call_count, 1)

            # Second call with identical content should hit cache
            res2 = tag_commercial_chunk_with_llm("Governing law shall be the State of New York.", filename="gov.pdf")
            self.assertEqual(res1, res2)
            self.assertEqual(mock_post.call_count, 1, "Cache hit should not trigger additional HTTP request!")


if __name__ == "__main__":
    unittest.main()
