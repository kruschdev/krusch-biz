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

    def test_09_detect_wrong_instrument_same_section(self):
        """Detect WRONG_INSTRUMENT when claim attributes section to SOW but authority is in MSA."""
        sow_and_msa_clauses = [
            {
                "section": "Section 4.1",
                "title": "Payment Terms",
                "agreement_title": "Master Services Agreement 2024",
                "instrument_type": "master_services_agreement",
                "content": "Customer shall pay within thirty (30) days ('Net 30').",
                "structured_slots": {"net_days": 30},
                "superseded": False,
                "terminated": False
            }
        ]
        # Draft explicitly attributes Section 4.1 to SOW instead of MSA
        draft = "Under SOW Section 4.1, Customer shall remit payment within thirty (30) days ('Net 30')."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, sow_and_msa_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["wrong_instruments"], 1)
        self.assertEqual(claims[0]["failure_mode"], "WRONG_INSTRUMENT")

    def test_10_word_and_number_normalization_net_thirty(self):
        """Verify spoken words 'thirty (30)' align with normalized slot 'Net 30'."""
        draft = "Pursuant to Section 4.1, Customer shall remit payment within Net 30 days."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertTrue(is_grounded)
        self.assertEqual(claims[0]["status"], "verified_grounded")

    def test_11_detect_currency_and_rate_basis_divergence(self):
        """Detect currency mismatch (€ vs $) and interest rate basis mismatch (APR vs monthly)."""
        # 1. Currency divergence: €500,000 vs $500,000
        draft_curr = "Pursuant to Section 10.1, aggregate cumulative liability is capped at €500,000."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft_curr, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["divergent_terms"], 1)
        self.assertIn("Currency mismatch", claims[0]["details"])

        # 2. Rate basis divergence: 18% APR vs 1.5% per month
        payment_clause_with_rate = [
            {
                "section": "Section 4.1",
                "title": "Payment Terms",
                "content": "Undisputed overdue balances accrue late interest of 1.5% per month.",
                "structured_slots": {"late_interest_pct": 1.5},
                "superseded": False,
                "terminated": False
            }
        ]
        draft_rate = "Pursuant to Section 4.1, overdue balances accrue late interest of 18% APR."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft_rate, payment_clause_with_rate)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["divergent_terms"], 1)
        self.assertIn("Rate unit mismatch", claims[0]["details"])

    def test_12_detect_dropped_carveout_negation(self):
        """Detect NEGATED_OBLIGATION when an assertion asserts absolute cap dropping gross negligence carve-outs."""
        carveout_clauses = [
            {
                "section": "Section 10.1",
                "title": "Limitation of Liability",
                "content": "Each party's aggregate liability shall be capped at $500,000, except for gross negligence or willful misconduct.",
                "structured_slots": {"cap_amount": 500000.0, "carve_outs": ["gross_negligence", "willful_misconduct"]},
                "superseded": False,
                "terminated": False
            }
        ]
        # Dropping carve-outs
        draft = "Pursuant to Section 10.1, aggregate liability is capped at $500,000 for all claims without exception including gross negligence."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, carveout_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["negated_obligations"], 1)
        self.assertEqual(claims[0]["failure_mode"], "NEGATED_OBLIGATION")

    def test_13_amendment_modifies_one_slot_leaves_rest(self):
        """Verify that an amendment modifying Net 45 correctly validates Net 45 while catching invalid numbers."""
        amd_clauses = [
            {
                "section": "Section 4.1",
                "title": "Amended Payment Terms",
                "content": "Section 4.1 is amended: invoices payable Net 45 days.",
                "structured_slots": {"net_days": 45},
                "superseded": False,
                "terminated": False
            }
        ]
        # Legitimate assertion of amended term
        draft_good = "Pursuant to Section 4.1, invoices are payable within Net 45 days."
        is_grounded, _, _, stats = verify_commercial_grounding(draft_good, amd_clauses)
        self.assertTrue(is_grounded)
        self.assertEqual(stats["pass_rate"], 100.0)

        # Divergent assertion on amended term
        draft_bad = "Pursuant to Section 4.1, invoices are payable within Net 60 days."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft_bad, amd_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(claims[0]["failure_mode"], "DIVERGENT_TERM")

    def test_14_section_symbol_normalization(self):
        """Verify citation '§4.1' matches clause indexed under 'Section 4.1'."""
        draft = "Pursuant to §4.1, Customer shall pay all undisputed invoice amounts within thirty (30) days of invoice date ('Net 30')."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertTrue(is_grounded)
        self.assertEqual(stats["pass_rate"], 100.0)
        self.assertEqual(claims[0]["status"], "verified_grounded")

    def test_15_multiclaim_paragraph_partial_invention(self):
        """In a multi-claim paragraph where one claim is authentic and one is invented, fail grounding."""
        draft = (
            "Pursuant to Section 4.1, Customer shall pay all undisputed invoice amounts within thirty (30) days of invoice date. "
            "Under Section 99.9, Vendor must supply free hardware replacements."
        )
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["total_claims"], 2)
        self.assertEqual(stats["supported_claims"], 1)
        self.assertEqual(stats["invented_clauses"], 1)
        self.assertEqual(stats["pass_rate"], 50.0)

    def test_16_detect_partial_support_missing_number(self):
        """Detect PARTIAL_SUPPORT when claim sentence mentions payment obligation but omits the required net days."""
        draft = "Pursuant to Section 4.1, Customer shall pay all invoices in accordance with the billing schedule."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, self.mock_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["partial_supports"], 1)
        self.assertEqual(claims[0]["failure_mode"], "PARTIAL_SUPPORT")

    def test_17_ambiguous_citation_detection(self):
        """Detect AMBIGUOUS_CITATION when citation matches multiple distinct active agreements without qualification."""
        multi_ag_clauses = [
            {
                "agreement_id": 1,
                "agreement_title": "Master Services Agreement",
                "section": "Section 4.1",
                "content": "MSA Section 4.1: Net 30 payment terms.",
                "structured_slots": {"net_days": 30},
                "superseded": False,
                "terminated": False
            },
            {
                "agreement_id": 2,
                "agreement_title": "Statement of Work #1",
                "section": "Section 4.1",
                "content": "SOW Section 4.1: Deliverables inspection within 5 business days.",
                "structured_slots": {"inspection_days": 5},
                "superseded": False,
                "terminated": False
            }
        ]
        # Ambiguous citation: does not specify MSA or SOW
        draft = "Pursuant to Section 4.1, Customer shall remit payment within thirty (30) days."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, multi_ag_clauses)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["ambiguous_citations"], 1)
        self.assertEqual(claims[0]["failure_mode"], "AMBIGUOUS_CITATION")

    def test_18_numeric_claim_strict_slot_or_span_rejection(self):
        """Ensure token overlap CANNOT substantiate an unverified numeric claim."""
        # Clause specifies Net 30
        clause = [
            {
                "agreement_id": 1,
                "agreement_title": "Master Services Agreement",
                "section": "Section 4.1",
                "content": "Customer shall pay all undisputed invoice amounts within thirty (30) days of invoice date.",
                "structured_slots": {"net_days": 30},
                "superseded": False,
                "terminated": False
            }
        ]
        # Draft asserts 75 days, using high token overlap words from the clause
        draft = "Pursuant to Section 4.1, Customer shall pay all undisputed invoice amounts within 75 days of invoice date."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, clause)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["divergent_terms"], 1)
        self.assertEqual(claims[0]["failure_mode"], "DIVERGENT_TERM")

    def test_19_conditional_obligation_negation(self):
        """Detect NEGATED_OBLIGATION when an assertion asserts unconditional coverage dropping express exceptions."""
        conditional_clause = [
            {
                "agreement_id": 1,
                "agreement_title": "Master Services Agreement",
                "section": "Section 4.1",
                "content": "Invoices are payable Net 30, except for pre-approved rush orders which require immediate payment.",
                "structured_slots": {"net_days": 30},
                "superseded": False,
                "terminated": False
            }
        ]
        # Draft claims Net 30 applies to all orders without exception
        draft = "Pursuant to Section 4.1, invoices are payable Net 30 for all orders without exception."
        is_grounded, claims, _, stats = verify_commercial_grounding(draft, conditional_clause)
        self.assertFalse(is_grounded)
        self.assertEqual(stats["negated_obligations"], 1)
        self.assertEqual(claims[0]["failure_mode"], "NEGATED_OBLIGATION")


if __name__ == "__main__":
    unittest.main()
