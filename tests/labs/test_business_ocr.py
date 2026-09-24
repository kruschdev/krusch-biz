import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.labs.business_ocr import (
    clean_currency_str,
    heuristic_extract_invoice_data,
    parse_business_document,
    parse_date_string,
    validate_file_security,
)


class TestBusinessOCR(unittest.TestCase):
    def test_01_security_validation(self):
        # Valid file
        valid = validate_file_security("invoice_2026.pdf", 1024)
        self.assertEqual(valid, "invoice_2026.pdf")

        # Unsupported extension
        with self.assertRaises(ValueError):
            validate_file_security("malicious.exe", 1024)

        # File too large
        with self.assertRaises(ValueError):
            validate_file_security("huge.pdf", 25 * 1024 * 1024)

    def test_02_currency_and_date_parsers(self):
        self.assertEqual(clean_currency_str("$ 1,450.75"), 1450.75)
        self.assertEqual(clean_currency_str("USD 99.00"), 99.00)
        self.assertEqual(clean_currency_str("invalid"), 0.0)

        self.assertEqual(parse_date_string("2026-09-15"), "2026-09-15")
        self.assertEqual(parse_date_string("09/15/2026"), "2026-09-15")
        self.assertEqual(parse_date_string("September 15, 2026"), "2026-09-15")

    def test_03_heuristic_invoice_extraction(self):
        sample_invoice_text = """
        Apex Enterprise Software Inc.
        Invoice #: INV-2026-9042
        Date: 2026-09-01
        Payment Due: 2026-10-01
        Terms: Net 30
        Bill To: Acme Corporation

        Software Licensing Tier 3    1    $ 8,000.00    $ 8,000.00
        Dedicated Support Add-on     1    $ 2,000.00    $ 2,000.00

        Subtotal: $ 10,000.00
        Tax (8.25%): $ 825.00
        Total Amount Due: $ 10,825.00
        """

        data = heuristic_extract_invoice_data(sample_invoice_text, "sample_invoice.txt")
        self.assertEqual(data["doc_type"], "invoice")
        self.assertEqual(data["invoice_number"], "INV-2026-9042")
        self.assertEqual(data["invoice_date"], "2026-09-01")
        self.assertEqual(data["due_date"], "2026-10-01")
        self.assertEqual(data["subtotal"], 10000.0)
        self.assertEqual(data["tax_amount"], 825.0)
        self.assertEqual(data["total"], 10825.0)
        self.assertEqual(data["payment_terms"], "Net 30")
        self.assertGreaterEqual(data["confidence"]["overall"], 0.80)

    def test_04_parse_business_document_bytes(self):
        doc_bytes = b"Vendor: NovaCloud\nInvoice #INV-77\nTotal: $ 500.00\nDate: 2026-08-20"
        res = parse_business_document(doc_bytes, "bill.txt")
        self.assertEqual(res["invoice_number"], "INV-77")
        self.assertEqual(res["total"], 500.0)
