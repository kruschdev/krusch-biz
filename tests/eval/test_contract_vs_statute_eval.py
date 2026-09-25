"""
tests/eval/test_contract_vs_statute_eval.py
===========================================
Regression test gate for the 1-Command Cross-Engine Compliance Benchmark.
Executes the 11 end-to-end conflict test pairs and validates 100.0% convergence.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.eval_contract_vs_statute_join import run_benchmark


class TestContractVsStatuteEvalGate(unittest.TestCase):
    """Automated evaluation gate for the Contract-vs-Statute Join engine."""

    def test_all_11_compliance_pairs_pass(self):
        """All 11 statutory floor, ceiling, and waiver conflict pairs must achieve 100% convergence."""
        success = run_benchmark()
        self.assertTrue(success, "Contract-vs-Statute Join Benchmark must achieve 100% convergence across all 11 test pairs.")


if __name__ == "__main__":
    unittest.main()
