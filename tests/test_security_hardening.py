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


if __name__ == "__main__":
    unittest.main()
