import os
import sys
import unittest
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db
from src.backend.db import ContractPortfolio, Invoice, init_db
from src.backend.main import app, get_db


class TestBusinessOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        cls.TestingSessionLocal = sessionmaker(bind=cls.engine)
        init_db(cls.engine)

        def override_get_db():
            db = cls.TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        src.backend.db.SessionLocal = cls.TestingSessionLocal
        cls.client = TestClient(app)

    def test_01_register_contract_portfolio(self):
        exp_date = (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d")
        payload = {
            "contract_name": "Cloud Hosting Enterprise Agreement",
            "vendor": "HyperCloud Systems LLC",
            "contract_type": "Infrastructure MSA",
            "expiration_date": exp_date,
            "value": 120000.0,
            "auto_renew": True,
            "notes": "Mission critical GPU hosting cluster"
        }
        res = self.client.post("/api/business/contracts", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["contract_name"], "Cloud Hosting Enterprise Agreement")
        self.assertEqual(data["vendor"], "HyperCloud Systems LLC")
        self.assertTrue(data["days_until_expiration"] > 0)
        self.contract_id = data["id"]

    def test_02_list_and_filter_contracts(self):
        # Register a second contract expiring in 15 days
        exp_date = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        self.client.post("/api/business/contracts", json={
            "contract_name": "Software License Renewal",
            "vendor": "SaaS Platform Co",
            "contract_type": "SaaS License",
            "expiration_date": exp_date,
            "value": 15000.0
        })

        res = self.client.get("/api/business/contracts")
        self.assertEqual(res.status_code, 200)
        contracts = res.json()
        self.assertGreaterEqual(len(contracts), 2)

        # Test expiring endpoint (within 30 days)
        res_exp = self.client.get("/api/business/contracts/expiring?within_days=30")
        self.assertEqual(res_exp.status_code, 200)
        expiring = res_exp.json()
        self.assertGreaterEqual(len(expiring), 1)
        self.assertTrue(any(c["vendor"] == "SaaS Platform Co" for c in expiring))

    def test_03_create_invoice_with_calculations(self):
        due_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        payload = {
            "invoice_number": "INV-2026-8001",
            "client_name": "Zenith Media Corp",
            "client_email": "ap@zenithmedia.com",
            "tax_rate": 0.10,
            "due_date": due_date,
            "line_items": [
                {"description": "Commercial Advisory Sprint", "quantity": 2.0, "rate": 5000.0},
                {"description": "Contract Analysis Suite", "quantity": 1.0, "rate": 2500.0}
            ],
            "notes": "Wire payment instructions enclosed."
        }
        res = self.client.post("/api/business/invoices", json=payload)
        self.assertEqual(res.status_code, 201)
        inv = res.json()
        self.assertEqual(inv["invoice_number"], "INV-2026-8001")
        self.assertEqual(inv["subtotal"], 12500.0)  # 2*5000 + 2500
        self.assertEqual(inv["tax_amount"], 1250.0)  # 10%
        self.assertEqual(inv["total"], 13750.0)
        self.assertEqual(inv["status"], "draft")

    def test_04_invoice_lifecycle_and_outstanding(self):
        # Create an overdue invoice
        past_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        res_od = self.client.post("/api/business/invoices", json={
            "invoice_number": "INV-2026-OVERDUE",
            "client_name": "Lagging Payer LLC",
            "due_date": past_date,
            "line_items": [{"description": "Audit", "quantity": 1.0, "rate": 4000.0}]
        })
        self.assertEqual(res_od.status_code, 201)
        inv_id = res_od.json()["id"]

        # List invoices and check overdue flag
        res_list = self.client.get("/api/business/invoices")
        self.assertEqual(res_list.status_code, 200)
        items = res_list.json()
        overdue_item = next((i for i in items if i["id"] == inv_id), None)
        self.assertIsNotNone(overdue_item)
        self.assertTrue(overdue_item["is_overdue"])
        self.assertEqual(overdue_item["status"], "overdue")

        # Check outstanding summary metrics
        res_ar = self.client.get("/api/business/invoices/outstanding")
        self.assertEqual(res_ar.status_code, 200)
        ar = res_ar.json()
        self.assertIn("metrics", ar)
        self.assertGreater(ar["metrics"]["total_outstanding"], 0)
        self.assertGreater(ar["metrics"]["total_overdue"], 0)

        # Transition status to paid
        res_pay = self.client.patch(f"/api/business/invoices/{inv_id}/status", json={"status": "paid"})
        self.assertEqual(res_pay.status_code, 200)
        self.assertEqual(res_pay.json()["status"], "paid")
