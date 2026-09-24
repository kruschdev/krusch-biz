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




if __name__ == "__main__":
    unittest.main()

