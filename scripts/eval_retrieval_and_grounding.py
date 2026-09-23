#!/usr/bin/env python3
"""
scripts/eval_retrieval_and_grounding.py
=======================================
Empirical evaluation scorecard and golden CI benchmark for KruschBiz.
Evaluates:
  1. Recall@1 (Top-1 statutory/contractual citation accuracy)
  2. Recall@5 (Top-5 coverage of governing agreements)
  3. Mean Reciprocal Rank (MRR)
  4. Forbidden Distractor & Stale Agreement Leak Count
  5. Assertion-Level Grounding Pass Rate (%)
  6. Query Retrieval Latency (ms)
"""

import json
import os
import sys
import time
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite:///kruschbiz_eval.db")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.db import SessionLocal, init_db
from src.backend.ingest import ingest_mock_data
from src.backend.rag import retrieve_clauses, verify_commercial_grounding


def run_golden_evaluation(
    dataset_path: str,
    db_session=None,
    limit: int = 5
) -> dict[str, Any]:
    """Execute evaluation benchmark against the golden evaluation set."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases: list[dict[str, Any]] = json.load(f)

    db = db_session or SessionLocal()
    own_session = db_session is None

    top1_hits = 0
    top5_hits = 0
    reciprocal_ranks = []
    distractor_leaks = 0
    latencies = []
    grounding_passes = 0
    total_assertions_checked = 0

    try:
        for case in cases:
            query = case["fact_pattern"]
            gold_sections = [s.lower() for s in case["gold_sections"]]
            distractors = [d.lower() for d in case.get("forbidden_distractors", [])]

            start_t = time.time()
            retrieved = retrieve_clauses(db=db, query=query, limit=limit)
            latency = (time.time() - start_t) * 1000.0
            latencies.append(latency)

            retrieved_sections = [c.get("section", "").lower() for c in retrieved]

            # Top-1 check
            if retrieved_sections and any(g in retrieved_sections[0] for g in gold_sections):
                top1_hits += 1

            # Top-5 coverage & Reciprocal Rank
            hit_rank = 0
            for rank, r_sec in enumerate(retrieved_sections, start=1):
                if any(g in r_sec for g in gold_sections):
                    hit_rank = rank
                    break

            if hit_rank > 0:
                top5_hits += 1
                reciprocal_ranks.append(1.0 / hit_rank)
            else:
                reciprocal_ranks.append(0.0)

            # Distractor check
            for r_sec in retrieved_sections:
                if any(d in r_sec for d in distractors):
                    distractor_leaks += 1

            # Grounding check on expected claims
            expected_claims = case.get("expected_claims", [])
            if expected_claims:
                synthetic_draft = " ".join([f"Pursuant to {gold_sections[0].title()}, {claim}." for claim in expected_claims])
                is_grounded, claims_audit, _, stats = verify_commercial_grounding(synthetic_draft, retrieved)
                total_assertions_checked += stats.get("total_claims", 0)
                grounding_passes += stats.get("supported_claims", 0)

        total_cases = len(cases)
        recall_at_1 = (top1_hits / total_cases) * 100.0
        recall_at_5 = (top5_hits / total_cases) * 100.0
        mrr = sum(reciprocal_ranks) / total_cases
        avg_latency = sum(latencies) / total_cases
        grounding_pass_rate = (grounding_passes / max(total_assertions_checked, 1)) * 100.0

        metrics = {
            "total_eval_cases": total_cases,
            "recall_at_1": round(recall_at_1, 2),
            "recall_at_5": round(recall_at_5, 2),
            "mrr": round(mrr, 4),
            "distractor_leaks": distractor_leaks,
            "grounding_pass_rate": round(grounding_pass_rate, 2),
            "average_latency_ms": round(avg_latency, 2)
        }
        return metrics

    finally:
        if own_session:
            db.close()


def print_scorecard(metrics: dict[str, Any]):
    print("\n" + "=" * 75)
    print(" 💼 KRUSCHBIZ EMPIRICAL EVALUATION SCORECARD (GOLDEN BENCHMARK)")
    print("=" * 75)
    print(f" Total Evaluation Cases   : {metrics['total_eval_cases']}")
    print(f" Recall@1 (Top-1 Accuracy): {metrics['recall_at_1']}%  (Target: > 85.0%)")
    print(f" Recall@5 (Top-5 Coverage): {metrics['recall_at_5']}% (Target: > 95.0%)")
    print(f" Mean Reciprocal Rank     : {metrics['mrr']}   (Target: > 0.900)")
    print(f" Distractor Leaks         : {metrics['distractor_leaks']}      (Target: 0)")
    print(f" Grounding Pass Rate      : {metrics['grounding_pass_rate']}% (Target: > 90.0%)")
    print(f" Average Latency          : {metrics['average_latency_ms']} ms")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    ingest_mock_data(db)
    db.close()

    dataset_file = os.path.join(PROJECT_ROOT, "data", "eval", "golden_business_eval.json")
    results = run_golden_evaluation(dataset_file)
    print_scorecard(results)
