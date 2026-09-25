"""
tests/test_taxonomy_slots.py
============================
Unit tests verifying typed structured slot extraction, exact span provenance,
and trigger discrimination:
  - Exact span provenance: text[char_start:char_end] == raw_span
  - Schema adherence: {value, unit, raw_span, char_start, char_end, pattern_id, confidence}
  - Trigger discrimination: Retainers & fees ($25k) vs Liability caps ($1M)
  - Trigger discrimination: Breach cure notice vs payment dispute vs suspension vs termination
  - Backward compatibility helpers: get_slot_val, slot_dict_to_primitives
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.taxonomy import (
    CANONICAL_TOPICS,
    TOPIC_LIMITATION_OF_LIABILITY,
    TOPIC_PAYMENT_TERMS,
    TOPIC_SLA_PERFORMANCE,
    TOPIC_TERMINATION,
    extract_structured_slots,
    get_slot_val,
    normalize_topic,
    slot_dict_to_primitives,
)


class TestTaxonomyTypedSlots(unittest.TestCase):

    def test_01_canonical_topics_and_normalization(self):
        """Verify unified 13+ canonical commercial topics and alias mappings."""
        self.assertIn("PAYMENT_TERMS", CANONICAL_TOPICS)
        self.assertIn("LIABILITY_CAP", CANONICAL_TOPICS)
        self.assertIn("LIMITATION_OF_LIABILITY", CANONICAL_TOPICS)
        self.assertIn("SLA_UPTIME", CANONICAL_TOPICS)
        self.assertIn("SLA_PERFORMANCE", CANONICAL_TOPICS)
        self.assertIn("GOVERNING_LAW", CANONICAL_TOPICS)

        self.assertEqual(normalize_topic("LIABILITY_CAP"), TOPIC_LIMITATION_OF_LIABILITY)
        self.assertEqual(normalize_topic("SLA_UPTIME"), TOPIC_SLA_PERFORMANCE)
        self.assertEqual(normalize_topic("TERMINATION_CONVENIENCE"), TOPIC_TERMINATION)

    def test_02_typed_slot_schema_and_span_provenance(self):
        """Verify that extracted slots follow {value, unit, raw_span, char_start, char_end, pattern_id, confidence}."""
        text = "Section 4.1 Payment Terms: Invoices are payable under Net 45 terms with 1.5% per month late interest."
        topic, slots = extract_structured_slots(text)

        self.assertEqual(topic, TOPIC_PAYMENT_TERMS)
        self.assertIn("net_days", slots)
        self.assertIn("late_interest_pct", slots)

        net_slot = slots["net_days"]
        # Required keys check
        for key in ("value", "unit", "raw_span", "char_start", "char_end", "pattern_id", "confidence"):
            self.assertIn(key, net_slot, f"Missing key '{key}' in typed slot.")

        self.assertEqual(net_slot["value"], 45)
        self.assertEqual(net_slot["unit"], "days")
        self.assertEqual(net_slot["raw_span"], "Net 45")
        # Character span verification
        self.assertEqual(text[net_slot["char_start"]:net_slot["char_end"]], net_slot["raw_span"])
        self.assertGreater(net_slot["confidence"], 0.9)

        interest_slot = slots["late_interest_pct"]
        self.assertEqual(interest_slot["value"], 1.5)
        self.assertEqual(interest_slot["unit"], "%/month")
        self.assertEqual(text[interest_slot["char_start"]:interest_slot["char_end"]], interest_slot["raw_span"])

    def test_03_trigger_discrimination_caps_vs_fees(self):
        """Verify that monetary fees/retainers are NOT mistakenly attributed as liability caps."""
        fee_text = (
            "Section 3.1 Consulting Fees: Customer shall pay a fixed monthly retainer fee of $25,000 "
            "for cloud infrastructure engineering services."
        )
        _, fee_slots = extract_structured_slots(fee_text)

        self.assertNotIn("cap_amount", fee_slots, "Fee was wrongly classified as liability cap!")
        self.assertIn("fee_amount", fee_slots)
        self.assertEqual(fee_slots["fee_amount"]["value"], 25000.0)
        self.assertEqual(fee_slots["fee_amount"]["unit"], "USD")

        cap_text = (
            "Section 12.1 Limitation of Liability: In no event shall either party's aggregate liability "
            "under this Agreement exceed $1,000,000 or the total fees paid."
        )
        _, cap_slots = extract_structured_slots(cap_text)

        self.assertIn("cap_amount", cap_slots, "Liability cap was missed!")
        self.assertEqual(cap_slots["cap_amount"]["value"], 1000000.0)
        self.assertEqual(cap_slots["cap_amount"]["unit"], "USD")
        self.assertEqual(cap_slots["cap_amount"]["raw_span"], "$1,000,000")

    def test_04_trigger_discrimination_notice_windows(self):
        """Verify separation of breach cure notice from invoice disputes, suspension, and termination."""
        cure_text = (
            "Section 11.2 Termination for Cause: A party may terminate if the defaulting party fails to "
            "cure such material breach within thirty (30) business days to cure following written notice."
        )
        _, cure_slots = extract_structured_slots(cure_text)
        self.assertIn("cure_days", cure_slots)
        self.assertEqual(cure_slots["cure_days"]["value"], 30)

        dispute_text = (
            "Customer must provide notice to dispute any invoice within ten (10) days of the invoice date."
        )
        _, dispute_slots = extract_structured_slots(dispute_text)
        self.assertIn("payment_dispute_notice_days", dispute_slots)
        self.assertEqual(dispute_slots["payment_dispute_notice_days"]["value"], 10)

        suspension_text = (
            "Vendor may suspend cloud hosting services upon ten (10) business days prior written notice if delinquent."
        )
        _, susp_slots = extract_structured_slots(suspension_text)
        self.assertIn("delinquency_notice_days", susp_slots)
        self.assertEqual(susp_slots["delinquency_notice_days"]["value"], 10)

        term_text = (
            "Either party may terminate for convenience upon sixty (60) days prior written notice."
        )
        _, term_slots = extract_structured_slots(term_text)
        self.assertIn("termination_notice_days", term_slots)
        self.assertEqual(term_slots["termination_notice_days"]["value"], 60)

    def test_05_backward_compatibility_helpers(self):
        """Verify get_slot_val and slot_dict_to_primitives work with both typed and primitive formats."""
        typed_slots = {
            "net_days": {
                "value": 30,
                "unit": "days",
                "raw_span": "Net 30",
                "char_start": 0,
                "char_end": 6,
                "pattern_id": "test",
                "confidence": 0.99
            },
            "late_interest_pct": 1.5,  # legacy primitive
        }

        self.assertEqual(get_slot_val(typed_slots["net_days"]), 30)
        self.assertEqual(get_slot_val(typed_slots["late_interest_pct"]), 1.5)

        prims = slot_dict_to_primitives(typed_slots)
        self.assertEqual(prims, {"net_days": 30, "late_interest_pct": 1.5})

    def test_06_tightened_net_days_rejects_non_payment(self):
        """Verify 'net 30 kg' or 'Net 10 users' is NOT mistakenly extracted as payment net_days."""
        non_payment_text = "The server payload requires net 30 kg weight limit and Net 10 users capacity."
        _, slots = extract_structured_slots(non_payment_text)
        self.assertNotIn("net_days", slots, "Extracted net_days from weight/user specifications!")

    def test_07_notice_days_not_blocked_by_net_days(self):
        """Verify that general notice days are extracted even when net_days is present (independent namespaces)."""
        combined_text = (
            "Customer shall pay invoices Net 30 days. Either party shall give at least fifteen (15) days prior written notice."
        )
        _, slots = extract_structured_slots(combined_text)
        self.assertIn("net_days", slots)
        self.assertEqual(slots["net_days"]["value"], 30)
        self.assertIn("notice_days", slots, "notice_days was blocked by net_days!")
        self.assertEqual(slots["notice_days"]["value"], 15)

    def test_08_slot_spans_and_taxonomy_version(self):
        """Verify get_slot_spans returns character offsets and TAXONOMY_VERSION == 3."""
        from src.backend.taxonomy import TAXONOMY_VERSION, get_slot_spans
        self.assertEqual(TAXONOMY_VERSION, 3)

        text = "Invoices are payable Net 45 days."
        _, slots = extract_structured_slots(text)
        spans = get_slot_spans(slots)
        self.assertIn("net_days", spans)
        self.assertEqual(spans["net_days"]["raw_span"], "Net 45")
        self.assertEqual(text[spans["net_days"]["char_start"]:spans["net_days"]["char_end"]], "Net 45")


if __name__ == "__main__":
    unittest.main()
