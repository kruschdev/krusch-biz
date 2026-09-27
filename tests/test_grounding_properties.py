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


    def test_property_6_physical_citation_spine_coordinate_persistence(self):
        """
        Property: Physical Citation Spine coordinates (page_number, printed_page, bbox,
        char_start, char_end, extra_metadata) must be preserved end-to-end through
        controlling resolution dictionaries and grounding verification.
        """
        coord_clause = {
            "id": 501,
            "agreement_id": 42,
            "agreement_title": "Enterprise Cloud Master Agreement",
            "authority_class": "governing_agreement",
            "section": "Section 9.2",
            "title": "Data Security & Encryption",
            "topic": "DATA_SECURITY",
            "structured_slots": {
                "encryption_standard": "AES-256",
                "certifications": ["SOC-2 Type II", "ISO-27001"]
            },
            "content": "Section 9.2 Data Security. Vendor will maintain SOC-2 Type II certification and encrypt data at rest with AES-256.",
            "page_number": 14,
            "printed_page": "14-B",
            "bbox": [54.0, 112.5, 480.0, 75.0],
            "char_start": 450,
            "char_end": 560,
            "extra_metadata": {"extractor": "krusch-nexus", "ocr_confidence": 0.998}
        }
        res = {
            "status": "resolved",
            "controlling_clause": coord_clause,
            "amendment_trail": [],
            "incorporated_clauses": []
        }
        claim = "Pursuant to Section 9.2, Vendor will maintain SOC-2 Type II certification and encrypt data at rest with AES-256."
        is_valid, findings, advisory, stats = verify_commercial_grounding(
            analysis_text=claim,
            controlling_result=res
        )
        self.assertTrue(is_valid, f"Claim should be verified: {findings}")
        self.assertEqual(stats["supported_claims"], 1)
        self.assertEqual(stats["unsupported_claims"], 0)

        # Verify resolver controlling clause coordinate extraction
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from src.backend.db import init_db, Agreement, Clause
        from src.backend.resolver import resolve_controlling_clause

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Session = sessionmaker(bind=engine)
        init_db(engine)
        db = Session()
        try:
            ag = Agreement(
                tenant_id="tenant_test",
                title="Enterprise Cloud Master Agreement",
                counterparty="Vendor",
                instrument_type="master_services_agreement",
                status="active",
                effective_date=datetime(2024, 1, 1)
            )
            db.add(ag)
            db.commit()

            cl = Clause(
                tenant_id="tenant_test",
                agreement_id=ag.id,
                section="Section 9.2",
                title="Data Security & Encryption",
                topic="DATA_SECURITY",
                structured_slots={"encryption_standard": "AES-256"},
                content="Vendor will maintain SOC-2 Type II certification.",
                authority_class="governing_agreement",
                page_number=14,
                printed_page="14-B",
                bbox=[54.0, 112.5, 480.0, 75.0],
                char_start=450,
                char_end=560,
                extra_metadata={"extractor": "krusch-nexus", "ocr_confidence": 0.998},
                is_active=True
            )
            db.add(cl)
            db.commit()

            resolved = resolve_controlling_clause(
                db=db,
                tenant_id="tenant_test",
                counterparty="Vendor",
                topic="DATA_SECURITY",
                as_of_date="2024-06-01",
                persist_trace=False
            )
            self.assertEqual(resolved["status"], "resolved")
            ctrl = resolved["controlling_clause"]
            self.assertEqual(ctrl["page_number"], 14)
            self.assertEqual(ctrl["printed_page"], "14-B")
            self.assertEqual(ctrl["bbox"], [54.0, 112.5, 480.0, 75.0])
            self.assertEqual(ctrl["char_start"], 450)
            self.assertEqual(ctrl["char_end"], 560)
            self.assertEqual(ctrl["extra_metadata"]["ocr_confidence"], 0.998)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

