import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.config import is_loopback_or_private_host, is_strict_loopback, settings


class TestConfig(unittest.TestCase):
    def test_default_ports(self):
        self.assertEqual(settings.BACKEND_PORT, 8086)
        self.assertEqual(settings.FRONTEND_PORT, 8506)
        self.assertEqual(settings.DATABASE_PORT, 5436)

    def test_loopback_validator(self):
        self.assertTrue(is_loopback_or_private_host("localhost"))
        self.assertTrue(is_loopback_or_private_host("127.0.0.1"))
        self.assertTrue(is_loopback_or_private_host("http://127.0.0.1:8086"))
        self.assertTrue(is_loopback_or_private_host("http://localhost:8506"))
        self.assertTrue(is_loopback_or_private_host("192.168.1.50"))
        self.assertTrue(is_loopback_or_private_host("10.0.0.1"))
        self.assertFalse(is_loopback_or_private_host("8.8.8.8"))
        self.assertFalse(is_loopback_or_private_host("https://api.openai.com"))

    def test_strict_loopback_and_logging_on_invalid_hosts(self):
        self.assertTrue(is_strict_loopback("127.0.0.1"))
        self.assertTrue(is_strict_loopback("localhost"))
        self.assertFalse(is_strict_loopback("192.168.1.50"))
        with self.assertLogs("src.backend.config", level="DEBUG") as cm:
            self.assertFalse(is_loopback_or_private_host("not_an_ip_or_local_host.example.com"))
            self.assertFalse(is_strict_loopback("not_an_ip_or_local_host.example.com"))
        self.assertTrue(any("Host validation failed" in msg for msg in cm.output))
        self.assertTrue(any("Strict loopback validation failed" in msg for msg in cm.output))

    def test_allowed_ingest_dirs(self):
        dirs = settings.allowed_ingest_dirs_list
        self.assertTrue(len(dirs) >= 1)
        self.assertTrue(any("data" in d for d in dirs))


if __name__ == "__main__":
    unittest.main()
