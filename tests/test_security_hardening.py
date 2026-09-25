"""
tests/test_security_hardening.py
================================
Unit tests verifying security boundaries and hardening:
  - Mandatory API_KEY outside development environment
  - Strict loopback bind enforcement unless ALLOW_LAN=1
  - MIME magic byte verification
  - Chunk count DOS protection
"""

import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.config import Settings, validate_security_invariants
from src.backend.ingest import validate_file_magic_bytes


class TestSecurityHardening(unittest.TestCase):

    def test_01_api_key_required_outside_development(self):
        """Verify that server refuses to bind outside dev without API_KEY."""
        s = Settings(APP_ENV="production", API_KEY=None, HOST="127.0.0.1")
        with self.assertRaises(RuntimeError) as ctx:
            validate_security_invariants(s)
        self.assertIn("API_KEY is strictly required", str(ctx.exception))

    def test_02_api_key_accepted_in_production(self):
        """Verify that server starts in production with valid API_KEY."""
        s = Settings(APP_ENV="production", API_KEY="secret-key-123", HOST="127.0.0.1")
        # Should not raise
        validate_security_invariants(s)

    def test_03_refuse_binding_0_0_0_0_without_allow_lan(self):
        """Verify that server refuses to bind 0.0.0.0 unless ALLOW_LAN=1."""
        s = Settings(APP_ENV="development", HOST="0.0.0.0", ALLOW_LAN=False)
        with self.assertRaises(RuntimeError) as ctx:
            validate_security_invariants(s)
        self.assertIn("Refusing to bind to non-loopback host", str(ctx.exception))

    def test_04_allow_lan_binding_with_flag(self):
        """Verify that 0.0.0.0 bind is accepted when ALLOW_LAN=1."""
        s = Settings(APP_ENV="development", HOST="0.0.0.0", ALLOW_LAN=True)
        # Should not raise
        validate_security_invariants(s)

    def test_05_mime_magic_bytes_validation(self):
        """Verify that declared extensions are checked against file magic bytes."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.7 valid pdf header content")
            valid_pdf = f.name

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"NOT A REAL PDF FILE HEADER")
            fake_pdf = f.name

        try:
            self.assertTrue(validate_file_magic_bytes(valid_pdf, ".pdf"))
            self.assertFalse(validate_file_magic_bytes(fake_pdf, ".pdf"))
        finally:
            if os.path.exists(valid_pdf):
                os.remove(valid_pdf)
            if os.path.exists(fake_pdf):
                os.remove(fake_pdf)

    def test_06_tenant_binding_and_spoofing_rejected(self):
        """Verify that API keys bound to a specific tenant reject mismatched X-Tenant-ID headers."""
        from fastapi import HTTPException
        from src.backend.main import verify_api_key
        import src.backend.main as main_mod

        old_api_key = main_mod.settings.API_KEY
        try:
            main_mod.settings.API_KEY = "test_secret_123"

            # 1. Matching tenant binding passes
            result = verify_api_key(
                x_api_key="tenant_alpha:test_secret_123",
                x_tenant_id="tenant_alpha"
            )
            self.assertEqual(result, "tenant_alpha:test_secret_123")

            # 2. Header spoofing: key is bound to tenant_alpha, but header claims tenant_beta -> 403 Forbidden
            with self.assertRaises(HTTPException) as ctx:
                verify_api_key(
                    x_api_key="tenant_alpha:test_secret_123",
                    x_tenant_id="tenant_beta"
                )
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("Tenant header spoofing rejected", str(ctx.exception.detail))

            # 3. Invalid secret key -> 401 Unauthorized
            with self.assertRaises(HTTPException) as ctx:
                verify_api_key(
                    x_api_key="tenant_alpha:wrong_secret",
                    x_tenant_id="tenant_alpha"
                )
            self.assertEqual(ctx.exception.status_code, 401)
        finally:
            main_mod.settings.API_KEY = old_api_key

    def test_07_rate_limiter_sliding_window(self):
        """Verify SimpleRateLimiter blocks requests exceeding threshold."""
        from src.backend.main import SimpleRateLimiter

        limiter = SimpleRateLimiter(requests_per_minute=3)
        self.assertTrue(limiter.check("client_1"))
        self.assertTrue(limiter.check("client_1"))
        self.assertTrue(limiter.check("client_1"))
        # 4th request within window rejected
        self.assertFalse(limiter.check("client_1"))
        # Separate client not affected
        self.assertTrue(limiter.check("client_2"))

    def test_08_embeddings_mock_refusal_in_consult(self):
        """Verify that get_embeddings_batch refuses constant fallback vectors."""
        from unittest.mock import patch
        from src.backend.rag import _real_get_embeddings_batch, RetrievalError, embedding_cache

        embedding_cache.clear()
        # Simulate Ollama offline / failing via httpx
        with patch("httpx.Client.post", side_effect=Exception("Connection refused")):
            with self.assertRaises(RetrievalError) as ctx:
                _real_get_embeddings_batch(["Sample clause text unique query for refusal test 999"])
            self.assertIn("CANNOT_DRAFT_EMBEDDINGS_UNAVAILABLE", str(ctx.exception))



    def test_09_fail_boot_on_empty_and_default_api_keys_outside_dev(self):
        """Verify that server refuses to boot outside development with empty or default placeholder keys."""
        for bad_key in ("", "   ", "default", "changeme", "secret", "kruschbiz_secret", "replace_me"):
            s = Settings(APP_ENV="production", API_KEY=bad_key, HOST="127.0.0.1")
            with self.assertRaises(RuntimeError) as ctx:
                validate_security_invariants(s)
            self.assertIn("API_KEY is strictly required outside development environment", str(ctx.exception))

    def test_10_mime_magic_rejects_mz_elf_and_html_disguised_pdf(self):
        """Verify that executable magic bytes (MZ, ELF) and HTML disguised as PDF are rejected."""
        # 1. Windows MZ header disguised as PDF and DOCX
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00")
            mz_pdf = f.name
        # 2. Linux ELF header disguised as PDF and TXT
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00")
            elf_pdf = f.name
        # 3. HTML disguised as PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"<!DOCTYPE html>\n<html><head><title>Invoice</title></head><body><h1>Fake</h1></body></html>")
            html_pdf = f.name
        # 4. Lowercase HTML tag disguised as PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"<html><body><script>malicious()</script></body></html>")
            script_pdf = f.name
        # 5. Valid PDF header
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.7 \x25\xe2\xe3\xcf\xd3\n")
            valid_pdf = f.name

        try:
            self.assertFalse(validate_file_magic_bytes(mz_pdf, ".pdf"))
            self.assertFalse(validate_file_magic_bytes(mz_pdf, ".docx"))
            self.assertFalse(validate_file_magic_bytes(mz_pdf, ".txt"))

            self.assertFalse(validate_file_magic_bytes(elf_pdf, ".pdf"))
            self.assertFalse(validate_file_magic_bytes(elf_pdf, ".txt"))

            self.assertFalse(validate_file_magic_bytes(html_pdf, ".pdf"))
            self.assertFalse(validate_file_magic_bytes(script_pdf, ".pdf"))

            self.assertTrue(validate_file_magic_bytes(valid_pdf, ".pdf"))
        finally:
            for p in (mz_pdf, elf_pdf, html_pdf, script_pdf, valid_pdf):
                if os.path.exists(p):
                    os.remove(p)

    def test_11_audit_log_immutability_update_and_delete_raise_permission_error(self):
        """Verify that AuditLog records are append-only; UPDATE and DELETE trigger PermissionError."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from src.backend.db import Base, AuditLog

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        log = AuditLog(
            tenant_id="tenant_sec",
            action="consult",
            actor_key_hash="hash_12345",
            client_ip="127.0.0.1"
        )
        session.add(log)
        session.commit()
        log_id = log.id

        # 1. Verify UPDATE fails
        log_fetched = session.query(AuditLog).filter_by(id=log_id).first()
        log_fetched.actor_key_hash = "tampered_hash"
        with self.assertRaises(PermissionError) as ctx:
            session.commit()
        self.assertIn("AuditLog records are append-only and strictly immutable", str(ctx.exception))
        session.rollback()

        # 2. Verify DELETE fails
        log_to_delete = session.query(AuditLog).filter_by(id=log_id).first()
        session.delete(log_to_delete)
        with self.assertRaises(PermissionError) as ctx:
            session.commit()
        self.assertIn("AuditLog records are append-only and strictly immutable", str(ctx.exception))
        session.rollback()
        session.close()

    def test_12_transactional_purge_leaves_zero_rows_across_all_tables(self):
        """Verify that hard transactional purges leave exactly 0 leftover rows across all related tables."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from datetime import datetime
        from src.backend.db import (
            Base, DealMatter, DealEvidence, CommercialGroundingReport,
            Agreement, Clause, AgreementRelation, CommercialClauseVector,
            purge_deal_matter_transactional, purge_agreement_transactional
        )

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        tenant = "tenant_purge_audit"

        # A. Seed Deal Matter and relations
        deal = DealMatter(
            tenant_id=tenant,
            deal_code="DEAL-ZERO-LEFTOVER",
            title="Acquisition Zero",
            context_facts="Diligence background facts",
            company_name="Our Corp",
            counterparty_name="Target Co",
            status="active"
        )
        session.add(deal)
        session.flush()

        ev1 = DealEvidence(tenant_id=tenant, deal_id=deal.id, filename="c1.pdf", content="Evidence 1 content")
        ev2 = DealEvidence(tenant_id=tenant, deal_id=deal.id, filename="c2.pdf", content="Evidence 2 content")
        rep1 = CommercialGroundingReport(
            id="rep-12345",
            tenant_id=tenant,
            deal_id=deal.id,
            claims_json="[]",
            total_claims=0
        )
        session.add_all([ev1, ev2, rep1])

        # B. Seed Agreement and relations
        ag = Agreement(
            tenant_id=tenant,
            title="Purge Master Agreement",
            instrument_type="master_agreement",
            counterparty="Target Co",
            effective_date=datetime(2024, 1, 1),
            execution_status="executed"
        )
        session.add(ag)
        session.flush()

        cl1 = Clause(tenant_id=tenant, agreement_id=ag.id, section="1.1", title="Term", topic="PAYMENT_TERMS", authority_class="governing_agreement", content="Content 1")
        cl2 = Clause(tenant_id=tenant, agreement_id=ag.id, section="1.2", title="Fee", topic="FEES", authority_class="governing_agreement", content="Content 2")
        rel1 = AgreementRelation(tenant_id=tenant, source_agreement_id=ag.id, target_agreement_id=ag.id, relation_type="AMENDS", clause_scope="ALL", status="confirmed")
        vec1 = CommercialClauseVector(
            tenant_id=tenant,
            organization="Our Corp",
            agreement_type="master_agreement",
            title=ag.title,
            section="1.1",
            topic="PAYMENT_TERMS",
            content="Content 1",
            authority_class="governing_agreement"
        )
        session.add_all([cl1, cl2, rel1, vec1])
        session.commit()

        # Execute Deal Purge
        deal_stats = purge_deal_matter_transactional(session, tenant, deal.id)
        self.assertEqual(deal_stats["deleted"], 1)
        self.assertEqual(deal_stats["evidence"], 2)
        self.assertEqual(deal_stats["reports"], 1)

        # Assert 0 leftover rows for deal tables
        self.assertEqual(session.query(DealMatter).filter_by(tenant_id=tenant).count(), 0)
        self.assertEqual(session.query(DealEvidence).filter_by(tenant_id=tenant).count(), 0)
        self.assertEqual(session.query(CommercialGroundingReport).filter_by(tenant_id=tenant).count(), 0)

        # Execute Agreement Purge
        ag_stats = purge_agreement_transactional(session, tenant, ag.id)
        self.assertEqual(ag_stats["deleted"], 1)

        # Assert 0 leftover rows for agreement tables
        self.assertEqual(session.query(Agreement).filter_by(tenant_id=tenant).count(), 0)
        self.assertEqual(session.query(Clause).filter_by(tenant_id=tenant).count(), 0)
        self.assertEqual(session.query(AgreementRelation).filter_by(tenant_id=tenant).count(), 0)
        self.assertEqual(session.query(CommercialClauseVector).filter_by(tenant_id=tenant).count(), 0)

        session.close()


if __name__ == "__main__":
    unittest.main()

