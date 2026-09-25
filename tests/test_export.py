import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.export import generate_brief_docx, generate_brief_markdown


class TestExport(unittest.TestCase):
    def setUp(self):
        self.sample_brief = (
            "# I. KEY COMMERCIAL TERMS & TRANSACTION OVERVIEW\n"
            "This transaction involves cloud hosting services with Net 30 payment terms.\n\n"
            "## II. MATERIAL RISK EXPOSURE & CARVE-OUTS\n"
            "Limitation of liability is capped at 12 months fees paid under Section 10.1.\n"
        )
        self.sample_claims = [
            {
                "claim_id": "c1",
                "sentence": "Pursuant to Section 10.1, liability is capped at 12 months fees.",
                "cited_authority": "Section 10.1",
                "status": "verified_grounded",
                "failure_mode": None
            },
            {
                "claim_id": "c2",
                "sentence": "Under Clause 99.9, full hardware warranty applies.",
                "cited_authority": "Clause 99.9",
                "status": "invented_clause",
                "failure_mode": "INVENTED_CLAUSE"
            }
        ]
        self.sample_clauses = [
            {
                "section": "Section 10.1",
                "title": "Limitation of Liability",
                "organization": "Acme Corp",
                "authority_class": "governing_agreement",
                "content": "Liability shall not exceed 12 months fees paid."
            }
        ]

    def test_01_generate_brief_docx_validity(self):
        docx_bytes = generate_brief_docx(
            brief_content=self.sample_brief,
            deal_title="Acme Cloud Procurement",
            deal_code="DEAL-2026-TEST",
            counterparty="CloudScale AI",
            claims_audit=self.sample_claims,
            retrieved_clauses=self.sample_clauses
        )
        self.assertIsInstance(docx_bytes, bytes)
        self.assertTrue(len(docx_bytes) > 1000)
        # Check ZIP / DOCX magic bytes (PK\x03\x04)
        self.assertEqual(docx_bytes[:4], b"PK\x03\x04")

    def test_02_generate_brief_markdown_formatting(self):
        md = generate_brief_markdown(
            brief_content=self.sample_brief,
            deal_title="Acme Cloud Procurement",
            deal_code="DEAL-2026-TEST",
            counterparty="CloudScale AI",
            claims_audit=self.sample_claims,
            retrieved_clauses=self.sample_clauses
        )
        self.assertIn("EXECUTIVE COMMERCIAL MEMORANDUM", md)
        self.assertIn("DEAL-2026-TEST", md)
        self.assertIn("APPENDIX A: ASSERTION-LEVEL COMMERCIAL GROUNDING AUDIT", md)
        self.assertIn("APPENDIX B: TABLE OF CONTRACTUAL AUTHORITIES RETRIEVED", md)
        self.assertIn("Section 10.1", md)

    def test_03_generate_what_controls_export(self):
        from src.backend.export import generate_what_controls_export
        resolutions = [
            {
                "topic": "PAYMENT_TERMS",
                "status": "resolved",
                "confidence": 0.95,
                "controlling_clause": {
                    "agreement_title": "Master Services Agreement",
                    "section": "Section 4.1",
                    "structured_slots": {"net_days": 30}
                },
                "amendment_trail": [
                    {
                        "relation": "AMENDS",
                        "scope": "Section 4.1",
                        "from_agreement_title": "Amendment No. 1",
                        "to_agreement_title": "Master Services Agreement",
                        "effective_date": "2024-02-01"
                    }
                ],
                "resolution_rationale": "Resolved via explicit 1-hop amendment walk."
            }
        ]
        res = generate_what_controls_export(
            counterparty="VendorCorp",
            as_of_date="2024-06-01",
            resolutions=resolutions
        )
        self.assertEqual(res["counterparty"], "VendorCorp")
        self.assertEqual(res["as_of_date"], "2024-06-01")
        self.assertEqual(res["topics_evaluated"], 1)
        self.assertIn("GENERAL COUNSEL CONTROLLING TERMS MEMORANDUM", res["markdown"])
        self.assertIn("VendorCorp", res["markdown"])
        self.assertIn("PAYMENT_TERMS", res["markdown"])
        self.assertIn("AMENDMENT PRECEDENCE LINEAGE & AUDIT TRAIL", res["markdown"])


if __name__ == "__main__":
    unittest.main()
