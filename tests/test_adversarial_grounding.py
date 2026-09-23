"""
tests/test_adversarial_grounding.py
===================================
Adversarial test suite verifying commercial assertion grounding failure detection.
Tests deliberate attack patterns:
  - Invented / phantom clauses
  - Divergent numerical slots (payment terms, uptime, liability caps)
  - Superseded / inoperative agreements
  - Guardrail refusal when authorities are absent or superseded
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.rag import generate_executive_brief, verify_commercial_grounding


class TestAdversarialGrounding(unittest.TestCase):

    def setUp(self):
        self.mock_clauses = [
            {
                "section": "Section 4.1",
                "title": "Payment Terms",
                "authority_class": "governing_agreement",
                "content": "Customer shall pay all undisputed invoice amounts within thirty (30) days of invoice date ('Net 30').",
                "structured_slots": {"net_days": 30},
                "superseded": False,
                "terminated": False
            },
            {
                "section": "Section 10.1",
                "title": "Limitation of Liability",
                "authority_class": "governing_agreement",
                "content": "Each party's aggregate cumulative liability shall be capped at five hundred thousand dollars ($500,000).",
                "structured_slots": {"cap_amount": 500000.0},
                "superseded": False,
                "terminated": False
            },
            {
                "section": "Exhibit B Section 2.1",
                "title": "SLA Uptime",
                "authority_class": "amendment_addendum",
                "content": "Vendor warrants a Monthly Uptime Percentage of at least 99.9%.",
                "structured_slots": {"uptime_pct": 99.9},
                "superseded": False,
                "terminated": False
            },
            {
                "section": "Section 2021-MSA-4.1",
                "title": "Old Expired MSA",
                "authority_class": "governing_agreement",
                "content": "SUPERSEDED: Net 90 payment terms.",
                "structured_slots": {"net_days": 90},
                "superseded": True,
                "terminated": True,
                "superseded_by": "2025 MSA"
            }
        ]

    def test_01_detect_phantom_invented_clause(self):
        draft = "Under Section 99.9, Vendor must supply free hardware replacements."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["invented_clauses"], 1)
        self.assertEqual(claims[0]["failure_mode"], "INVENTED_CLAUSE")

    def test_02_detect_superseded_agreement_citation(self):
        draft = "Under Section 2021-MSA-4.1, Customer is entitled to Net 90 payment terms."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["superseded_terms"], 1)
        self.assertEqual(claims[0]["failure_mode"], "SUPERSEDED_TERM")

    def test_03_detect_divergent_payment_terms_slot(self):
        draft = "Pursuant to Section 4.1, Customer shall remit payment within sixty (60) days ('Net 60')."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["divergent_terms"], 1)
        self.assertEqual(claims[0]["failure_mode"], "DIVERGENT_TERM")

    def test_04_detect_inflated_liability_cap(self):
        draft = "Pursuant to Section 10.1, aggregate cumulative liability is capped at $2,000,000."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["divergent_terms"], 1)
        self.assertEqual(claims[0]["failure_mode"], "DIVERGENT_TERM")

    def test_05_detect_deflated_uptime_percentage(self):
        draft = "Pursuant to Exhibit B Section 2.1, Vendor guarantees 95.0% uptime availability."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["divergent_terms"], 1)
        self.assertEqual(claims[0]["failure_mode"], "DIVERGENT_TERM")

    def test_06_verify_authentic_grounded_assertion(self):
        draft = "Pursuant to Section 4.1, Customer shall pay all undisputed invoice amounts within thirty (30) days of invoice date."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertTrue(is_grounded)
        self.assertEqual(stats["pass_rate"], 100.0)
        self.assertEqual(claims[0]["status"], "verified_grounded")

    def test_07_refusal_when_no_authorities_present(self):
        brief, stats, _ = generate_executive_brief("Mystery Deal", "Some transaction", [])
        self.assertTrue(brief.startswith("CANNOT_DRAFT_WITHOUT_AUTHORITIES"))
        self.assertEqual(stats["refusal_reason"], "CANNOT_DRAFT_WITHOUT_AUTHORITIES")

    def test_08_refusal_when_all_authorities_superseded(self):
        superseded_only = [self.mock_clauses[3]]
        brief, stats, _ = generate_executive_brief("Old Deal", "Transaction", superseded_only)
        self.assertTrue(brief.startswith("REFUSAL_ALL_AUTHORITIES_SUPERSEDED"))
        self.assertEqual(stats["refusal_reason"], "REFUSAL_ALL_AUTHORITIES_SUPERSEDED")


if __name__ == "__main__":
    unittest.main()
