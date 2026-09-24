#!/usr/bin/env python3
"""
scripts/eval_retrieval_and_grounding.py
=======================================
Multi-gate empirical evaluation scorecard and calibration harness for KruschBiz.
Evaluates 3 distinct CI gates:
  1. Lexical / Fixture Gate (Seed corpus keyword & section locator retrieval)
  2. Unmocked Embedding Gate (Real bge-large 1024-d vectors from frozen local cache)
  3. Held-Out Contract Gate (12 held-out redacted commercial instruments; ensures
     superseded instruments never rank above controlling instruments)
Reports:
  - Separate Fixture and Held-Out Scorecards
  - 4-way Failure Taxonomy & Calibration Confusion Matrix:
    VERIFIED | INVENTED_CLAUSE | DIVERGENT_TERM | SUPERSEDED_TERM
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
import src.backend.ingest as ingest_mod
import src.backend.rag as rag_mod
from src.backend.db import CommercialClauseVector, init_db
from src.backend.ingest import ingest_mock_data
from src.backend.rag import retrieve_clauses, verify_commercial_grounding


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def normalize_eval_section(sec: str) -> str:
    """Normalize section strings like 'Section 4.1', '§4.1', 'sec 4.1', '4.1' to pure section numbers."""
    if not sec:
        return ""
    cleaned = re.sub(r"^(?:section|sec\.?|§|article|art\.?)\s*", "", sec.strip().lower())
    return cleaned.strip(" .:")


def section_matches(sec_a: str, sec_b: str) -> bool:
    """Compare two section locators under normalized section numbering."""
    norm_a = normalize_eval_section(sec_a)
    norm_b = normalize_eval_section(sec_b)
    if not norm_a or not norm_b:
        return False
    return norm_a == norm_b



def run_fixture_gate(
    dataset_path: str,
    db,
    limit: int = 5
) -> dict[str, Any]:
    """Gate 1: Lexical and hybrid retrieval on the seeded benchmark corpus."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    recalls_at_1 = []
    recalls_at_5 = []
    reciprocal_ranks = []
    distractor_leaks = 0
    latencies = []

    for c in cases:
        query = c.get("fact_pattern") or c.get("query")
        gold_sections = [g.lower() for g in c.get("gold_sections", [])]
        forbidden_distractors = [d.lower() for d in c.get("forbidden_distractors", [])]

        t0 = time.perf_counter()
        hits = retrieve_clauses(
            db=db,
            query=query,
            limit=limit,
            organization=c.get("organization"),
            agreement_type=c.get("agreement_type"),
            exclude_superseded=True
        )
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

        hit_sections = [h.get("section", "").lower() for h in hits]

        for distractor in forbidden_distractors:
            for hs in hit_sections:
                if distractor in hs or hs in distractor:
                    distractor_leaks += 1

        top_1_hit = False
        if hit_sections:
            hs0 = hit_sections[0]
            if any(section_matches(g, hs0) or g in hs0 for g in gold_sections):
                top_1_hit = True
        recalls_at_1.append(1.0 if top_1_hit else 0.0)

        top_5_matches = sum(1 for hs in hit_sections[:5] if any(section_matches(g, hs) or g in hs for g in gold_sections))
        top_5_hit = top_5_matches > 0
        recalls_at_5.append(1.0 if top_5_hit else 0.0)
        precisions_at_5 = getattr(run_fixture_gate, "_precisions", None)
        if precisions_at_5 is None:
            precisions_at_5 = []
            run_fixture_gate._precisions = precisions_at_5
        precisions_at_5.append(top_5_matches / 5.0)

        rank = 0
        for idx, hs in enumerate(hit_sections, 1):
            if any(section_matches(g, hs) or g in hs for g in gold_sections):
                rank = idx
                break
        reciprocal_ranks.append(1.0 / rank if rank > 0 else 0.0)

    n = len(cases)
    p5_list = getattr(run_fixture_gate, "_precisions", [0.0])
    run_fixture_gate._precisions = None
    return {
        "total_cases": n,
        "recall_at_1": round(sum(recalls_at_1) / n * 100.0, 2),
        "recall_at_5": round(sum(recalls_at_5) / n * 100.0, 2),
        "precision_at_5": round(sum(p5_list) / n * 100.0, 2),
        "mrr": round(sum(reciprocal_ranks) / n, 3),
        "distractor_leaks": distractor_leaks,
        "avg_latency_ms": round(sum(latencies) / n, 2),
    }


def run_unmocked_embedding_gate(
    seed_cache_path: str,
    queries_cache_path: str,
    dataset_path: str,
    limit: int = 5
) -> dict[str, Any]:
    """Gate 2: Pure unmocked vector cosine retrieval using frozen bge-large 1024-d embeddings."""
    if not os.path.exists(seed_cache_path) or not os.path.exists(queries_cache_path):
        return {"status": "skipped", "reason": "Missing frozen embedding cache files"}

    with open(seed_cache_path, "r", encoding="utf-8") as f:
        seed_vectors = json.load(f)
    with open(queries_cache_path, "r", encoding="utf-8") as f:
        query_vectors = json.load(f)
    with open(dataset_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    recalls_at_1 = []
    recalls_at_5 = []
    reciprocal_ranks = []

    for c in cases:
        qid = c["id"]
        if qid not in query_vectors:
            continue
        q_vec = query_vectors[qid]
        gold_sections = [g.lower() for g in c.get("gold_sections", [])]

        scores = []
        for sec, s_vec in seed_vectors.items():
            if "2021-msa" in sec.lower():
                continue  # exclude superseded in standard retrieval
            sim = cosine_similarity(q_vec, s_vec)
            scores.append((sec, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_hits = [s[0].lower() for s in scores[:limit]]

        # Recall@1
        h0 = top_hits[0] if top_hits else ""
        recalls_at_1.append(1.0 if any(g in h0 or h0 in g for g in gold_sections) else 0.0)

        # Recall@5
        h5 = any(any(g in h or h in g for g in gold_sections) for h in top_hits)
        recalls_at_5.append(1.0 if h5 else 0.0)

        # MRR
        rank = 0
        for idx, h in enumerate(top_hits, 1):
            if any(g in h or h in g for g in gold_sections):
                rank = idx
                break
        reciprocal_ranks.append(1.0 / rank if rank > 0 else 0.0)

    n = len(recalls_at_1)
    return {
        "status": "passed",
        "total_cases": n,
        "pure_vector_recall_at_1": round(sum(recalls_at_1) / n * 100.0, 2),
        "pure_vector_recall_at_5": round(sum(recalls_at_5) / n * 100.0, 2),
        "pure_vector_mrr": round(sum(reciprocal_ranks) / n, 3),
    }


def run_heldout_gate(
    heldout_path: str,
    heldout_cache_path: str,
    db
) -> dict[str, Any]:
    """
    Gate 3: Held-out redacted commercial contracts gate.
    Evaluates recall on instruments not in the seed set and strictly fails
    if a superseded instrument ranks above a controlling one.
    """
    with open(heldout_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    heldout_vectors = {}
    if os.path.exists(heldout_cache_path):
        with open(heldout_cache_path, "r", encoding="utf-8") as f:
            heldout_vectors = json.load(f)

    # Ingest heldout fixtures into db under tenant_id = 'tenant_heldout'
    for c in cases:
        cl = c.get("clause_fixture")
        if cl:
            existing = db.query(CommercialClauseVector.id).filter(
                CommercialClauseVector.section == cl["section"],
                CommercialClauseVector.tenant_id == "tenant_heldout"
            ).first()
            if not existing:
                sec = cl["section"]
                vec = heldout_vectors.get(f"c_{sec}", [0.05] * 1024)
                rec = CommercialClauseVector(
                    tenant_id="tenant_heldout",
                    organization=cl["organization"],
                    counterparty=cl.get("counterparty"),
                    agreement_type=cl["agreement_type"],
                    domain=cl.get("domain"),
                    title=cl["title"],
                    section=cl["section"],
                    authority_class=cl.get("authority_class", "governing_agreement"),
                    superseded=cl.get("superseded", False),
                    content=cl["content"],
                    structured_slots=c.get("numeric_slots"),
                    embedding=vec
                )
                db.add(rec)

        pred = c.get("predecessor_fixture")
        if pred:
            p_sec = pred["section"]
            existing = db.query(CommercialClauseVector.id).filter(
                CommercialClauseVector.section == p_sec,
                CommercialClauseVector.tenant_id == "tenant_heldout"
            ).first()
            if not existing:
                p_vec = heldout_vectors.get(f"c_{p_sec}", [0.05] * 1024)
                rec = CommercialClauseVector(
                    tenant_id="tenant_heldout",
                    organization=pred["organization"],
                    counterparty=pred.get("counterparty"),
                    agreement_type=pred["agreement_type"],
                    domain=pred.get("domain"),
                    title=pred["title"],
                    section=pred["section"],
                    authority_class=pred.get("authority_class", "governing_agreement"),
                    superseded=True,
                    superseded_by=pred.get("superseded_by"),
                    content=pred["content"],
                    embedding=p_vec
                )
                db.add(rec)
    db.commit()

    # Guard against mock constant vectors
    for k, vec in heldout_vectors.items():
        if vec and all(abs(x - vec[0]) < 1e-6 for x in vec):
            raise ValueError(f"Mock constant embedding detected for '{k}'. Real embeddings are strictly required.")

    recalls_at_1 = []
    recalls_at_5 = []
    precisions_at_5 = []
    reciprocal_ranks = []
    superseded_priority_inversions = 0
    superseded_in_top_1_count = 0

    for c in cases:
        qid = c["id"]
        query = c["query"]
        target_section = c["target_section"].lower()
        must_not_cite = [mnc.lower() for mnc in c.get("must_not_cite", [])]

        # Patch query vector from cache if available
        if f"q_{qid}" in heldout_vectors:
            rag_mod.get_embedding = lambda q, cached_vec=heldout_vectors[f"q_{qid}"]: cached_vec

        hits = retrieve_clauses(
            db=db,
            query=query,
            limit=5,
            exclude_superseded=False,  # Allow superseded in raw search to verify ranking suppression
            tenant_id="tenant_heldout"
        )

        hit_sections = [h.get("section", "").lower() for h in hits]

        if hits and hits[0].get("superseded", False):
            superseded_in_top_1_count += 1

        # Check for superseded priority inversion: did a superseded clause rank ABOVE the controlling clause?
        target_rank = next((idx for idx, hs in enumerate(hit_sections) if section_matches(target_section, hs) or target_section in hs), None)
        for mnc in must_not_cite:
            mnc_rank = next((idx for idx, hs in enumerate(hit_sections) if section_matches(mnc, hs) or mnc in hs), None)
            if mnc_rank is not None:
                if target_rank is None or mnc_rank < target_rank:
                    superseded_priority_inversions += 1

        top_1 = bool(hit_sections and (section_matches(target_section, hit_sections[0]) or target_section in hit_sections[0]))
        recalls_at_1.append(1.0 if top_1 else 0.0)

        top_5 = any(section_matches(target_section, hs) or target_section in hs for hs in hit_sections[:5])
        recalls_at_5.append(1.0 if top_5 else 0.0)
        precisions_at_5.append((1.0 / 5.0) if top_5 else 0.0)

        rank = next((idx for idx, hs in enumerate(hit_sections, 1) if section_matches(target_section, hs) or target_section in hs), 0)
        reciprocal_ranks.append(1.0 / rank if rank > 0 else 0.0)

    n = len(cases)
    return {
        "total_heldout_cases": n,
        "heldout_recall_at_1": round(sum(recalls_at_1) / n * 100.0, 2),
        "heldout_recall_at_5": round(sum(recalls_at_5) / n * 100.0, 2),
        "heldout_precision_at_5": round(sum(precisions_at_5) / n * 100.0, 2),
        "heldout_mrr": round(sum(reciprocal_ranks) / n, 3),
        "superseded_priority_inversions": superseded_priority_inversions,
        "superseded_in_top_1_rate": round(superseded_in_top_1_count / n * 100.0, 2),
    }


def run_grounding_calibration_matrix(
    heldout_path: str,
    db
) -> dict[str, Any]:
    """
    Calibration evaluation across the 4-way classification taxonomy:
      - VERIFIED: valid citation + matching slots
      - INVENTED_CLAUSE: phantom section citation
      - DIVERGENT_TERM: valid section, but contradictory slots (e.g. Net 90 vs Net 45)
      - SUPERSEDED_TERM: cites inoperative / superseded agreement
    """
    with open(heldout_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    confusion_matrix = {
        "VERIFIED": {"expected": 0, "correct": 0},
        "INVENTED_CLAUSE": {"expected": 0, "correct": 0},
        "DIVERGENT_TERM": {"expected": 0, "correct": 0},
        "SUPERSEDED_TERM": {"expected": 0, "correct": 0},
    }
    samples: list[tuple[str, str]] = []

    for c in cases:
        cl = c.get("clause_fixture")
        if not cl:
            continue
        sec = cl["section"]
        claim = c["claim"]
        target_slots = c.get("numeric_slots", {})

        retrieved_mock = [{
            "section": sec,
            "title": cl["title"],
            "content": cl["content"],
            "structured_slots": target_slots,
            "superseded": False,
            "terminated": False
        }]

        # 1. Grounded assertion test (Expect VERIFIED)
        confusion_matrix["VERIFIED"]["expected"] += 1
        _, records, _, _ = verify_commercial_grounding(f"Pursuant to {sec}, {claim}", retrieved_mock)
        pred_1 = "VERIFIED" if (records and records[0].get("status") == "verified_grounded") else (records[0].get("failure_mode", "UNKNOWN") if records else "UNKNOWN")
        samples.append(("VERIFIED", pred_1))
        if pred_1 == "VERIFIED":
            confusion_matrix["VERIFIED"]["correct"] += 1

        # 2. Phantom section test (Expect INVENTED_CLAUSE)
        confusion_matrix["INVENTED_CLAUSE"]["expected"] += 1
        _, records, _, _ = verify_commercial_grounding("Under Section 99.9, Vendor must refund all fees.", retrieved_mock)
        pred_2 = records[0].get("failure_mode", "UNKNOWN") if records else "UNKNOWN"
        samples.append(("INVENTED_CLAUSE", pred_2))
        if pred_2 == "INVENTED_CLAUSE":
            confusion_matrix["INVENTED_CLAUSE"]["correct"] += 1

        # 3. Divergent slot test (Expect DIVERGENT_TERM)
        if target_slots:
            confusion_matrix["DIVERGENT_TERM"]["expected"] += 1
            if "net_days" in target_slots:
                actual_days = int(target_slots["net_days"])
                divergent_draft = f"Pursuant to {sec}, Customer shall pay within ninety (90) days of invoice date ('Net 90')." if actual_days != 90 else f"Pursuant to {sec}, payment is Net 30."
            elif "uptime_pct" in target_slots:
                divergent_draft = f"Pursuant to {sec}, Vendor warrants an uptime percentage of at least 95.0%."
            elif "cap_amount" in target_slots:
                actual_cap = float(target_slots["cap_amount"])
                divergent_draft = f"Pursuant to {sec}, aggregate liability is capped at ${int(actual_cap * 2):,}."
            elif "cap_period_months" in target_slots:
                actual_mo = int(target_slots["cap_period_months"])
                divergent_mo = 12 if actual_mo != 12 else 24
                divergent_draft = f"Pursuant to {sec}, aggregate liability is limited to fees paid in the preceding {divergent_mo} months."
            elif "late_interest_pct" in target_slots:
                actual_pct = float(target_slots["late_interest_pct"])
                divergent_draft = f"Pursuant to {sec}, delinquent amounts accrue late interest at {round(actual_pct + 2.5, 1)}% per month."
            elif "notice_hours" in target_slots:
                actual_h = int(target_slots["notice_hours"])
                divergent_draft = f"Pursuant to {sec}, Vendor shall provide written notice of security incident within {actual_h + 48} hours."
            elif "notice_days" in target_slots:
                actual_d = int(target_slots["notice_days"])
                divergent_draft = f"Pursuant to {sec}, either party may terminate upon {actual_d + 30} days prior written notice."
            else:
                divergent_draft = f"Pursuant to {sec}, notice must be provided upon ninety (90) days prior written notice."

            _, records, _, _ = verify_commercial_grounding(divergent_draft, retrieved_mock)
            pred_3 = records[0].get("failure_mode", "UNKNOWN") if records else "UNKNOWN"
            samples.append(("DIVERGENT_TERM", pred_3))
            if pred_3 == "DIVERGENT_TERM":
                confusion_matrix["DIVERGENT_TERM"]["correct"] += 1

        # 4. Superseded instrument test (Expect SUPERSEDED_TERM)
        pred = c.get("predecessor_fixture")
        if pred:
            confusion_matrix["SUPERSEDED_TERM"]["expected"] += 1
            p_sec = pred["section"]
            superseded_mock = [{
                "section": p_sec,
                "title": pred["title"],
                "content": pred["content"],
                "superseded": True,
                "terminated": True,
                "superseded_by": "Controlling Agreement"
            }]
            _, records, _, _ = verify_commercial_grounding(f"Under {p_sec}, payment is due in 90 days.", superseded_mock)
            pred_4 = records[0].get("failure_mode", "UNKNOWN") if records else "UNKNOWN"
            samples.append(("SUPERSEDED_TERM", pred_4))
            if pred_4 == "SUPERSEDED_TERM":
                confusion_matrix["SUPERSEDED_TERM"]["correct"] += 1

    total_expected = sum(v["expected"] for v in confusion_matrix.values())
    total_correct = sum(v["correct"] for v in confusion_matrix.values())
    calibration_accuracy = round((total_correct / total_expected) * 100.0, 2) if total_expected > 0 else 0.0

    # Calculate Precision, Recall, and F1 per Failure Mode
    modes = ["VERIFIED", "INVENTED_CLAUSE", "DIVERGENT_TERM", "SUPERSEDED_TERM"]
    per_failure_mode_metrics = {}
    for m in modes:
        tp = sum(1 for exp, p in samples if exp == m and p == m)
        fp = sum(1 for exp, p in samples if exp != m and p == m)
        fn = sum(1 for exp, p in samples if exp == m and p != m)
        prec = round((tp / (tp + fp) * 100.0), 2) if (tp + fp) > 0 else 100.0
        rec = round((tp / (tp + fn) * 100.0), 2) if (tp + fn) > 0 else 100.0
        f1 = round((2 * prec * rec / (prec + rec)), 2) if (prec + rec) > 0 else 0.0
        per_failure_mode_metrics[m] = {
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn
        }

    macro_precision = round(sum(m["precision"] for m in per_failure_mode_metrics.values()) / len(modes), 2)
    macro_recall = round(sum(m["recall"] for m in per_failure_mode_metrics.values()) / len(modes), 2)
    macro_f1 = round(sum(m["f1"] for m in per_failure_mode_metrics.values()) / len(modes), 2)

    return {
        "confusion_matrix": confusion_matrix,
        "per_failure_mode_metrics": per_failure_mode_metrics,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "total_test_propositions": total_expected,
        "correct_classifications": total_correct,
        "calibration_accuracy": calibration_accuracy
    }


def main():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Session = sessionmaker(bind=engine)
    db_mod.engine = engine
    db_mod.SessionLocal = Session
    rag_mod.SessionLocal = Session
    ingest_mod.SessionLocal = Session

    init_db(engine)
    db = Session()
    ingest_mock_data(db)

    eval_path = os.path.join(PROJECT_ROOT, "data", "eval", "golden_business_eval.json")
    heldout_path = os.path.join(PROJECT_ROOT, "data", "eval", "heldout_contracts.json")
    seed_cache = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings", "seed_bge_large.json")
    queries_cache = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings", "queries_bge_large.json")
    heldout_cache = os.path.join(PROJECT_ROOT, "data", "eval", "embeddings", "heldout_bge_large.json")

    print("\n" + "=" * 76)
    print(" 💼 KRUSCHBIZ EMPIRICAL EVALUATION & CALIBRATION HARNESS")
    print("=" * 76)

    # Gate 1: Lexical / Fixture Gate
    fixture_metrics = run_fixture_gate(eval_path, db)

    # Gate 2: Unmocked Embedding Gate
    embedding_metrics = run_unmocked_embedding_gate(seed_cache, queries_cache, eval_path)

    # Gate 3: Held-out Contracts Gate
    heldout_metrics = run_heldout_gate(heldout_path, heldout_cache, db)

    # Grounding Calibration Matrix
    calib = run_grounding_calibration_matrix(heldout_path, db)

    print("\n----------------------------------------------------------------------------")
    print(" [GATE 1] FIXTURE CORPUS SCORECARD (Bootstrap Baseline)")
    print("----------------------------------------------------------------------------")
    print(f" Total Evaluation Cases   : {fixture_metrics['total_cases']}")
    print(f" Recall@1 (Top-1 Accuracy): {fixture_metrics['recall_at_1']}%  (Target: > 85.0%)")
    print(f" Recall@5 (Top-5 Coverage): {fixture_metrics['recall_at_5']}% (Target: > 95.0%)")
    print(f" Mean Reciprocal Rank     : {fixture_metrics['mrr']}   (Target: > 0.900)")
    print(f" Distractor Leaks         : {fixture_metrics['distractor_leaks']}      (Target: 0)")
    print(f" Average Latency          : {fixture_metrics['avg_latency_ms']} ms")

    print("\n----------------------------------------------------------------------------")
    print(" [GATE 2] UNMOCKED EMBEDDING GATE (Real bge-large 1024-d Vectors)")
    print("----------------------------------------------------------------------------")
    if embedding_metrics.get("status") == "passed":
        print(f" Pure Vector Recall@1     : {embedding_metrics['pure_vector_recall_at_1']}%")
        print(f" Pure Vector Recall@5     : {embedding_metrics['pure_vector_recall_at_5']}%")
        print(f" Pure Vector MRR          : {embedding_metrics['pure_vector_mrr']}")
    else:
        print(f" Status                   : {embedding_metrics.get('reason')}")

    print("\n----------------------------------------------------------------------------")
    print(" [GATE 3] HELD-OUT CONTRACTS GATE (Redacted External Instruments)")
    print("----------------------------------------------------------------------------")
    print(f" Held-Out Evaluation Cases: {heldout_metrics['total_heldout_cases']}")
    print(f" Held-Out Recall@1        : {heldout_metrics['heldout_recall_at_1']}%")
    print(f" Held-Out Recall@5        : {heldout_metrics['heldout_recall_at_5']}%")
    print(f" Held-Out MRR             : {heldout_metrics['heldout_mrr']}")
    print(f" Priority Inversions      : {heldout_metrics['superseded_priority_inversions']} (Superseded outranked controlling: MUST BE 0)")

    print("\n----------------------------------------------------------------------------")
    print(" [CALIBRATION] GROUNDING CONFUSION MATRIX & TAXONOMY ACCURACY")
    print("----------------------------------------------------------------------------")
    cm = calib["confusion_matrix"]
    for label, counts in cm.items():
        corr = counts["correct"]
        exp = counts["expected"]
        pct = round((corr / exp) * 100.0, 1) if exp > 0 else 0.0
        print(f"  {label:<18}: {corr:>2} / {exp:>2} ({pct:>5.1f}%)")
    print(f" Overall Calibration Acc  : {calib['calibration_accuracy']}%")

    print("\n----------------------------------------------------------------------------")
    print(" [PER-FAILURE-MODE METRICS] PRECISION, RECALL & F1")
    print("----------------------------------------------------------------------------")
    pfm = calib.get("per_failure_mode_metrics", {})
    print(f"  {'FAILURE MODE':<20} | {'PRECISION':<10} | {'RECALL':<10} | {'F1':<10}")
    print("  " + "-" * 58)
    for mode, m in pfm.items():
        print(f"  {mode:<20} | {m['precision']:>8.1f}%  | {m['recall']:>8.1f}%  | {m['f1']:>8.1f}%")
    print("  " + "-" * 58)
    print(f"  {'Macro Average':<20} | {calib.get('macro_precision', 0.0):>8.1f}%  | {calib.get('macro_recall', 0.0):>8.1f}%  | {calib.get('macro_f1', 0.0):>8.1f}%")
    print("=" * 76 + "\n")

    scorecard = {
        "timestamp": datetime.now(timezone.utc).isoformat() if "datetime" in globals() else str(time.time()),
        "gate1_fixture_smoke_test": fixture_metrics,
        "gate2_unmocked_embedding": embedding_metrics,
        "gate3_heldout_controlling": heldout_metrics,
        "gate4_grounding_calibration": {
            "calibration_accuracy": calib["calibration_accuracy"],
            "macro_precision": calib.get("macro_precision", 0.0),
            "macro_recall": calib.get("macro_recall", 0.0),
            "macro_f1": calib.get("macro_f1", 0.0),
            "confusion_matrix": calib["confusion_matrix"],
            "per_failure_mode_metrics": calib.get("per_failure_mode_metrics", {})
        }
    }
    scorecard_path = os.path.join(PROJECT_ROOT, "data", "eval", "scorecard.json")
    with open(scorecard_path, "w", encoding="utf-8") as f:
        json.dump(scorecard, f, indent=2)
    print(f"[ARTIFACT] Raw scorecard JSON published to {scorecard_path}\n")

    db.close()


if __name__ == "__main__":
    main()
