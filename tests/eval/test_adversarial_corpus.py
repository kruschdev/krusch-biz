"""
tests/eval/test_adversarial_corpus.py
======================================
Automated CI test verifying the 4 uncoupled empirical evaluation metrics
on the public adversarial multi-document family benchmark (adversarial_corpus.json):
  1. Relation Extraction F1 >= 85%
  2. Controlling Clause Accuracy As-Of Date >= 95%
  3. Slot Exact-Match Accuracy >= 95%
  4. Proposition Classification Accuracy >= 95%
"""

import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.eval_adversarial_corpus import run_adversarial_eval


@pytest.fixture(scope="module")
def eval_results():
    corpus_file = os.path.join(PROJECT_ROOT, "data/eval/adversarial_corpus.json")
    results = run_adversarial_eval(corpus_path=corpus_file, verbose=False)
    return results["metrics"]


def test_adversarial_relation_extraction_f1(eval_results):
    rel_metrics = eval_results["relation_extraction"]
    assert rel_metrics["f1"] >= 85.0, f"Relation F1 ({rel_metrics['f1']}%) fell below 85.0% threshold"
    assert rel_metrics["precision"] >= 85.0
    assert rel_metrics["recall"] >= 85.0


def test_adversarial_controlling_clause_accuracy(eval_results):
    cc_metrics = eval_results["controlling_clause_accuracy_as_of_date"]
    assert cc_metrics["accuracy_pct"] >= 95.0, f"Controlling clause accuracy ({cc_metrics['accuracy_pct']}%) fell below 95.0%"
    assert cc_metrics["correct_queries"] == cc_metrics["total_queries"]


def test_adversarial_slot_exact_match(eval_results):
    slot_metrics = eval_results["slot_exact_match"]
    assert slot_metrics["accuracy_pct"] >= 95.0, f"Slot exact-match accuracy ({slot_metrics['accuracy_pct']}%) fell below 95.0%"
    assert slot_metrics["matched_slots"] == slot_metrics["total_slots"]


def test_adversarial_proposition_grounding(eval_results):
    prop_metrics = eval_results["proposition_classification"]
    assert prop_metrics["accuracy_pct"] >= 95.0, f"Proposition classification accuracy ({prop_metrics['accuracy_pct']}%) fell below 95.0%"
    assert prop_metrics["correct_cases"] == prop_metrics["total_cases"]
