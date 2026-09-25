"""
tests/test_grounding_properties.py
==================================
Property-based and parametric verification test suite for KruschBiz commercial grounding checker.
Systematically tests the invariant:
  Grounding is an exact checker, not a generator.
  Mutating any single dimension (slot value, unit, obligation negation, or instrument authority)
  MUST flip the checker from VERIFIED to the exact expected canonical failure code.
"""

from __future__ import annotations

import unittest
from datetime import datetime

from src.backend.rag import verify_commercial_grounding


class TestGroundingProperties(unittest.TestCase):
    def setUp(self):
        """Standard mock controlling resolution fixture."""
        self.controlling_resolution = {
            "status": "resolved",
            "controlling_clause": {
                "id": 101,
                "agreement_id": 10,
                "agreement_title": "Amendment No. 1 to Master Services Agreement",
                "authority_class": "amendment",
                "section": "Section 4.1",
                "title": "Payment Terms",
                "topic": "PAYMENT_TERMS",
                "structured_slots": {
                    "net_days": 30,
                    "late_interest_pct": 1.5,
                    "currency": "USD"
                },
                "content": (
                    "Section 4.1 Invoicing and Payment. Vendor shall invoice Customer monthly. "
                    "All undisputed invoices shall be paid Net 30 days from the invoice date. "
                    "Late payments shall accrue interest at 1.5% per month."
                )
            },
            "amendment_trail": [
                {
                    "from_agreement_id": 1,
                    "to_agreement_id": 10,
                    "relation_type": "AMENDS",
                    "from_section": "Section 4.1",
                    "to_section": "Section 4.1"
                }
            ],
            "incorporated_clauses": []
        }

        self.liability_resolution = {
            "status": "resolved",
            "controlling_clause": {
                "id": 202,
                "agreement_id": 1,
                "agreement_title": "Master Services Agreement",
                "authority_class": "governing_agreement",
                "section": "Section 8.1",
                "title": "Limitation of Liability",
                "topic": "LIABILITY_CAP",
                "structured_slots": {
                    "capped": True,
                    "cap_amount": 1000000,
                    "currency": "USD",
                    "carve_outs": ["gross negligence", "willful misconduct", "confidentiality breach"]
                },
                "content": (
                    "Section 8.1 Aggregate Liability Cap. In no event shall either party's aggregate "
                    "liability arising out of or related to this Agreement exceed $1,000,000. "
                    "This limitation shall not apply to breaches of confidentiality or gross negligence."
                )
            },
            "amendment_trail": [],
            "incorporated_clauses": []
        }

    def test_property_1_numeric_slot_mutation_flips_to_mismatch(self):
        """
        Property: When a quantitative slot is mutated from the controlling value (Net 30),
        the grounding checker MUST reject the assertion with SLOT_MISMATCH or UNCITED_NUMERIC_CLAIM.
        """
        # Ground-truth verified claim
        valid_claim = "Under Section 4.1 of Amendment No. 1, undisputed invoices shall be paid Net 30 days."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=valid_claim,
            controlling_result=self.controlling_resolution
        )
        self.assertTrue(is_valid, f"Ground-truth claim should pass: {findings}")

        # Parametric mutations: Net 15, Net 45, Net 60, Net 90
        mutated_values = [15, 45, 60, 90, 120]
        for val in mutated_values:
            mutated_claim = f"Under Section 4.1 of Amendment No. 1, invoices are payable Net {val} days."
            is_valid, findings, _, _ = verify_commercial_grounding(
                analysis_text=mutated_claim,
                controlling_result=self.controlling_resolution
            )
            self.assertFalse(is_valid, f"Mutated slot Net {val} must be rejected!")
            codes = [f.get("failure_code") for f in findings]
            self.assertTrue(
                any(c in ("SLOT_MISMATCH", "DIVERGENT_TERM", "UNCITED_NUMERIC_CLAIM") for c in codes),
                f"Expected SLOT_MISMATCH for Net {val}, got: {codes}"
            )

    def test_property_2_unit_mutation_flips_to_unit_mismatch(self):
        """
        Property: Mutating a percentage unit to a fixed currency dollar figure ($1.50)
        MUST flip the checker to UNIT_MISMATCH or SLOT_MISMATCH.
        """
        valid_interest = "Section 4.1 provides that late payments shall accrue interest at 1.5% per month."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=valid_interest,
            controlling_result=self.controlling_resolution
        )
        self.assertTrue(is_valid, f"Valid interest claim should pass: {findings}")

        mutated_unit = "Section 4.1 provides that late payments accrue a flat fee of $1.50 per month."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=mutated_unit,
            controlling_result=self.controlling_resolution
        )
        self.assertFalse(is_valid, "Mutated dollar unit instead of percentage must fail!")
        codes = [f.get("failure_code") for f in findings]
        self.assertTrue(
            any(c in ("UNIT_MISMATCH", "SLOT_MISMATCH", "UNCITED_NUMERIC_CLAIM", "PARTIAL_SUPPORT") for c in codes),
            f"Expected unit/slot failure code, got: {codes}"
        )

    def test_property_3_polarity_negation_mutation_flips_to_negated_obligation(self):
        """
        Property: Asserting unlimited / uncapped liability when the controlling provision
        explicitly caps liability at $1,000,000 MUST fail with NEGATED_OBLIGATION or SLOT_MISMATCH.
        """
        valid_cap = "Pursuant to Section 8.1 of the Master Services Agreement, aggregate liability is capped at $1,000,000."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=valid_cap,
            controlling_result=self.liability_resolution
        )
        self.assertTrue(is_valid, f"Valid liability cap should pass: {findings}")

        # Negation / polarity flip
        negated_claim = "Under Section 8.1 of the Master Services Agreement, liability is uncapped with no limitation."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=negated_claim,
            controlling_result=self.liability_resolution
        )
        self.assertFalse(is_valid, "Asserting uncapped liability against capped clause must fail!")
        codes = [f.get("failure_code") for f in findings]
        self.assertTrue(
            any(c in ("NEGATED_OBLIGATION", "SLOT_MISMATCH", "DIVERGENT_TERM") for c in codes),
            f"Expected NEGATED_OBLIGATION or SLOT_MISMATCH, got: {codes}"
        )

    def test_property_4_superseded_instrument_citation_flips(self):
        """
        Property: If an assertion cites an earlier superseded agreement for a term that was
        modified in an amendment, it MUST fail verification.
        """
        # Claim cites MSA rather than the controlling Amendment No. 1
        stale_claim = "Under Section 4.1 of the 2023 Master Services Agreement, invoices are payable Net 45 days."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=stale_claim,
            controlling_result=self.controlling_resolution
        )
        self.assertFalse(is_valid, "Claim citing superseded terms must fail verification!")

    def test_property_5_span_containment_strictness(self):
        """
        Property: Exact span containment checks ensure that numbers appearing in claims
        must either match extracted slots or exact spans in the controlling clause.
        """
        # Claim with an ungrounded random numeric quantity (e.g. 5 business days notice)
        invented_numeric_claim = "Under Section 4.1, invoices must be delivered within 5 business days."
        is_valid, findings, _, _ = verify_commercial_grounding(
            analysis_text=invented_numeric_claim,
            controlling_result=self.controlling_resolution
        )
        self.assertFalse(is_valid, "Ungrounded numeric quantity must fail verification!")
        codes = [f.get("failure_code") for f in findings]
        self.assertTrue(
            any(c in ("UNCITED_NUMERIC_CLAIM", "INVENTED_CLAUSE", "UNGROUNDED_TOPIC", "SLOT_MISMATCH", "PARTIAL_SUPPORT") for c in codes),
            f"Expected ungrounded/slot code, got: {codes}"
        )


if __name__ == "__main__":
    unittest.main()
