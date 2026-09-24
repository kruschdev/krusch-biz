import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.labs.business_templates import (
    generate_commercial_document,
    get_commercial_template,
    list_commercial_templates,
    revise_commercial_document,
)


class TestBusinessTemplates(unittest.TestCase):
    def test_01_catalog_enumeration(self):
        templates = list_commercial_templates()
        self.assertGreaterEqual(len(templates), 5)
        ids = [t["id"] for t in templates]
        self.assertIn("commercial_nda", ids)
        self.assertIn("master_services_agreement", ids)
        self.assertIn("statement_of_work", ids)
        self.assertIn("independent_contractor", ids)
        self.assertIn("commercial_demand_letter", ids)

    def test_02_template_schema_retrieval(self):
        tmpl = get_commercial_template("commercial_nda")
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl["name"], "Mutual Non-Disclosure Agreement (NDA)")
        self.assertIn("fields", tmpl)
        field_keys = [f["key"] for f in tmpl["fields"]]
        self.assertIn("party_a", field_keys)
        self.assertIn("party_b", field_keys)

    def test_03_generate_nda(self):
        fields = {
            "party_a": "Krusch Dynamics",
            "party_b": "Pacific Ventures LLC",
            "purpose": "exploring joint enterprise venture",
            "term_years": 2,
            "governing_law": "State of California"
        }
        doc = generate_commercial_document("commercial_nda", fields)
        self.assertIn("MUTUAL NON-DISCLOSURE AGREEMENT", doc["document_content"])
        self.assertIn("Krusch Dynamics", doc["document_content"])
        self.assertIn("Pacific Ventures LLC", doc["document_content"])
        self.assertIn("2 year(s)", doc["document_content"])
        self.assertGreater(doc["word_count"], 150)

    def test_04_generate_demand_letter_dynamic_computation(self):
        fields = {
            "creditor_name": "Alpha Corp",
            "debtor_name": "Beta LLC",
            "invoice_number": "INV-990",
            "original_amount": 10000.0,
            "interest_accrued": 500.0,
            "cure_days": 7
        }
        doc = generate_commercial_document("commercial_demand_letter", fields)
        content = doc["document_content"]
        self.assertIn("FORMAL DEMAND FOR PAYMENT", content)
        self.assertIn("$10,500.00 USD", content)  # Auto-computed total
        self.assertIn("INV-990", content)

    def test_05_revise_document(self):
        orig = "The parties will submit disputes to court in New York."
        rev = revise_commercial_document(orig, "Make formal language and set California governing law")
        self.assertIn("shall", rev["revised_content"])
        self.assertIn("DraftPro", rev["revised_content"])
