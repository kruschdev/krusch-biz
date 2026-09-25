#!/usr/bin/env python3
"""
scripts/eval_adversarial_corpus.py
===================================
Production-grade empirical evaluation runner for the KruschBiz adversarial
multi-document corpus (data/eval/adversarial_corpus.json).

Scores 4 distinct, uncoupled metrics:
  1. Relation Extraction F1 (Precision, Recall, F1 against expected multi-doc edges)
  2. Controlling-Clause Accuracy As-Of Date (Temporal precedence graph walk accuracy)
  3. Slot Exact-Match Accuracy (Typed structured slot values with unit/span precision)
  4. Proposition Classification Accuracy (4-way calibration: VERIFIED, INVENTED_CLAUSE, DIVERGENT_TERM, SUPERSEDED_TERM)

Publishes granular breakdown and explicit failure diagnostics.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import sys
import time
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
from src.backend.db import Agreement, AgreementRelation, Clause
from src.backend.rag import verify_commercial_grounding
from src.backend.relations import extract_candidate_relations
from src.backend.resolver import resolve_controlling_clause
from src.backend.taxonomy import extract_structured_slots
from src.backend.tagger import tag_commercial_chunk


def normalize_eval_section(sec: str | None) -> str:
    """Normalize section locators (e.g. 'Section 4.1.', '§4.1', 'sec 4.1') to canonical form."""
    if not sec:
        return ""
    cleaned = re.sub(r"^(?:section|sec\.?|§|article|art\.?)\s*", "", sec.strip().lower())
    return cleaned.strip(" .:")


def section_matches(sec_a: str | None, sec_b: str | None) -> bool:
    """Determine if two section references match under normalization."""
    norm_a = normalize_eval_section(sec_a)
    norm_b = normalize_eval_section(sec_b)
    if not norm_a or not norm_b:
        return False
    return norm_a == norm_b


def run_adversarial_eval(
    corpus_path: str = os.path.join(PROJECT_ROOT, "data/eval/adversarial_corpus.json"),
    output_json_path: str | None = None,
    verbose: bool = True
) -> dict[str, Any]:
    """
    Execute end-to-end evaluation across all adversarial multi-document families.
    Returns comprehensive metrics dictionary.
    """
    if not os.path.exists(corpus_path):
        raise FileNotFoundError(f"Adversarial corpus fixture not found at: {corpus_path}")

    with open(corpus_path, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    families = corpus.get("families", [])

    # Global Metric Accumulators
    rel_tp = 0
    rel_fp = 0
    rel_fn = 0

    temporal_queries_total = 0
    temporal_queries_correct = 0

    slots_total = 0
    slots_matched = 0

    prop_cases = {
        "VERIFIED": {"expected": 0, "correct": 0},
        "INVENTED_CLAUSE": {"expected": 0, "correct": 0},
        "DIVERGENT_TERM": {"expected": 0, "correct": 0},
        "SUPERSEDED_TERM": {"expected": 0, "correct": 0},
    }

    family_results = []
    failures_log = []

    t_start = time.perf_counter()

    for fam in families:
        fam_id = fam["family_id"]
        fam_name = fam["name"]
        counterparty = fam["counterparty"]
        docs = fam.get("documents", [])
        expected_relations = fam.get("expected_relations", [])
        test_queries = fam.get("test_queries", [])

        # Isolated in-memory SQLite session per family
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        db_mod.Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        tenant_id = f"eval_{fam_id}"

        doc_id_to_ag: dict[str, Agreement] = {}
        extracted_candidate_edges: list[dict[str, Any]] = []

        # 1. Ingestion & Relation Extraction
        for d in docs:
            cp = d.get("counterparty_name") or counterparty
            eff_dt = datetime.strptime(d["effective_date"], "%Y-%m-%d").date() if d.get("effective_date") else None
            doc_hash = hashlib.sha256(d["text"].encode("utf-8")).hexdigest()
            ag = Agreement(
                tenant_id=tenant_id,
                title=d["title"],
                instrument_type=d["instrument_type"],
                counterparty=cp,
                effective_date=eff_dt,
                status="active" if d.get("execution_status", "executed") == "executed" else "draft",
                execution_status=d.get("execution_status", "executed"),
                source_filename=d["filename"],
                raw_hash=doc_hash
            )
            db.add(ag)
            db.flush()
            doc_id_to_ag[d["doc_id"]] = ag

            # Chunk document by sections
            chunks = re.split(r'\n+(?=(?:Section|Clause|Article|§|SCHEDULE|EXHIBIT|LETTER|OPERATIVE|RECITALS)\b)', d["text"])
            for idx, ch_text in enumerate(chunks):
                ch_text = ch_text.strip()
                if not ch_text:
                    continue
                sec_match = re.match(r'^(Section\s+[\d\.\w\-]+|Article\s+[\d\.\w\-]+|Schedule\s+[A-Z\d]+|Exhibit\s+[A-Z\d]+|Letter\s+Agreement)', ch_text, re.IGNORECASE)
                sec_name = sec_match.group(1) if sec_match else f"Section {idx}"
                topic, slots = extract_structured_slots(ch_text)
                tag_info = tag_commercial_chunk(content=ch_text, filename=d["filename"], locator=sec_name, doc_type=d["instrument_type"])
                assigned_topic = tag_info.get("topic") or topic
                cl = Clause(
                    tenant_id=tenant_id,
                    agreement_id=ag.id,
                    section=sec_name,
                    title=f"{d['title']} - {sec_name}",
                    topic=assigned_topic,
                    hierarchy_level="clause",
                    authority_class="statement_of_work" if "sow" in d["instrument_type"].lower() else "governing_agreement",
                    content=ch_text,
                    structured_slots=slots,
                    tags=json.dumps(tag_info.get("tags", [])),
                    summary=tag_info.get("summary"),
                    chunk_index=idx,
                    is_active=True
                )
                db.add(cl)
            db.flush()

            # Extract Candidate Relations
            cands = extract_candidate_relations(
                text=d["text"],
                filename=d["filename"],
                tenant_id=tenant_id,
                db=db,
                source_ag_id=ag.id,
                auto_persist_proposed=True
            )
            # Filter out negative evidence for graph edges evaluation
            real_cands = [c for c in cands if c.get("relation_type") != "NEGATIVE_EVIDENCE"]
            extracted_candidate_edges.extend(real_cands)

        # -------------------------------------------------------------
        # METRIC 1: Relation Extraction F1
        # -------------------------------------------------------------
        matched_expected = set()
        matched_extracted = set()

        for exp_idx, exp in enumerate(expected_relations):
            src_ag = doc_id_to_ag.get(exp["source_doc_id"])
            tgt_ag = doc_id_to_ag.get(exp["target_doc_id"])
            if not src_ag or not tgt_ag:
                continue

            for ext_idx, ext in enumerate(extracted_candidate_edges):
                if ext_idx in matched_extracted:
                    continue
                if (ext["source_agreement_id"] == src_ag.id and
                    ext["target_agreement_id"] == tgt_ag.id and
                    ext["relation_type"] == exp["relation_type"]):
                    # Optional clause scope check if specified
                    if "clause_scope" in exp and exp["clause_scope"] != "ALL":
                        if not section_matches(ext.get("clause_scope"), exp["clause_scope"]):
                            continue
                    matched_expected.add(exp_idx)
                    matched_extracted.add(ext_idx)
                    break

        fam_tp = len(matched_expected)
        fam_fn = len(expected_relations) - fam_tp
        fam_fp = len(extracted_candidate_edges) - len(matched_extracted)

        rel_tp += fam_tp
        rel_fn += fam_fn
        rel_fp += fam_fp

        if fam_fn > 0 or fam_fp > 0:
            for exp_idx, exp in enumerate(expected_relations):
                if exp_idx not in matched_expected:
                    failures_log.append({
                        "family_id": fam_id,
                        "type": "RELATION_FALSE_NEGATIVE",
                        "details": f"Expected relation {exp['relation_type']} {exp['source_doc_id']} -> {exp['target_doc_id']} not extracted"
                    })
            for ext_idx, ext in enumerate(extracted_candidate_edges):
                if ext_idx not in matched_extracted:
                    failures_log.append({
                        "family_id": fam_id,
                        "type": "RELATION_FALSE_POSITIVE",
                        "details": f"Unmatched proposed edge {ext['relation_type']} {ext.get('target_agreement_title')}"
                    })

        # Promote proposed relations to accepted to activate the precedence DAG
        db.query(AgreementRelation).filter(AgreementRelation.status == "proposed").update({"status": "accepted"})
        db.commit()

        # -------------------------------------------------------------
        # METRIC 2 & 3: Controlling-Clause Accuracy & Slot Exact-Match
        # -------------------------------------------------------------
        fam_queries_correct = 0
        fam_slots_matched = 0
        fam_slots_total = 0

        for q in test_queries:
            temporal_queries_total += 1
            query_cp = q.get("counterparty") or counterparty
            res = resolve_controlling_clause(
                db=db,
                tenant_id=tenant_id,
                counterparty=query_cp,
                topic=q["topic"],
                as_of_date=q["as_of_date"]
            )
            status = res.get("status")
            cc = res.get("controlling_clause") or {}
            win_title = cc.get("agreement_title")
            win_sec = cc.get("section")

            exp_status = q["expected_status"]
            exp_title = q.get("expected_agreement_title")
            exp_sec = q.get("expected_section")

            status_ok = (status == exp_status)
            title_ok = (win_title == exp_title) if exp_title else True
            sec_ok = section_matches(win_sec, exp_sec) if exp_sec else True

            query_passed = status_ok and title_ok and sec_ok
            if query_passed:
                temporal_queries_correct += 1
                fam_queries_correct += 1
            else:
                failures_log.append({
                    "family_id": fam_id,
                    "type": "CONTROLLING_CLAUSE_MISMATCH",
                    "details": (
                        f"Query topic={q['topic']} as_of={q['as_of_date']}: "
                        f"Expected status={exp_status}, winner='{exp_title}', sec='{exp_sec}'; "
                        f"Got status={status}, winner='{win_title}', sec='{win_sec}'"
                    )
                })

            # Check Slots
            exp_slots = q.get("expected_slots", {})
            if exp_slots:
                actual_slots = cc.get("structured_slots", {})
                for slot_key, exp_val in exp_slots.items():
                    slots_total += 1
                    fam_slots_total += 1
                    act_item = actual_slots.get(slot_key)
                    act_val = act_item.get("value") if isinstance(act_item, dict) else act_item
                    if act_val == exp_val:
                        slots_matched += 1
                        fam_slots_matched += 1
                    else:
                        failures_log.append({
                            "family_id": fam_id,
                            "type": "SLOT_VALUE_MISMATCH",
                            "details": f"Slot '{slot_key}' expected {exp_val}, got {act_val}"
                        })

        # -------------------------------------------------------------
        # METRIC 4: Proposition Classification Calibration
        # -------------------------------------------------------------
        # Test grounding assertions across the 4 canonical categories
        all_clauses = db.query(Clause).filter(Clause.tenant_id == tenant_id).all()
        substantive_clauses = [c for c in all_clauses if c.structured_slots]
        if substantive_clauses:
            test_cl = substantive_clauses[0]
            # Find the specific sentence within test_cl.content that contains the slot value/span
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', test_cl.content) if s.strip()]
            target_sentence = sentences[0]
            for s in sentences:
                if any(str(v.get("value") if isinstance(v, dict) else v) in s for v in test_cl.structured_slots.values()):
                    target_sentence = s
                    break

            if not target_sentence.lower().startswith("pursuant to") and not target_sentence.lower().startswith("under") and not target_sentence.lower().startswith("section"):
                target_sentence = f"Pursuant to {test_cl.section}, {target_sentence}"

            mock_retrieved = [{
                "section": test_cl.section,
                "title": test_cl.title,
                "content": test_cl.content,
                "structured_slots": test_cl.structured_slots,
                "superseded": False,
                "terminated": False
            }]

            # 1. VERIFIED case
            prop_cases["VERIFIED"]["expected"] += 1
            _, recs1, _, _ = verify_commercial_grounding(target_sentence, mock_retrieved)
            p1 = "VERIFIED" if (recs1 and recs1[0].get("status") == "verified_grounded") else (recs1[0].get("failure_mode", "UNKNOWN") if recs1 else "UNKNOWN")
            if p1 == "VERIFIED":
                prop_cases["VERIFIED"]["correct"] += 1
            else:
                failures_log.append({"family_id": fam_id, "type": "PROP_NOT_VERIFIED", "details": f"Expected VERIFIED, got {p1} on: '{target_sentence}'"})

            # 2. INVENTED_CLAUSE case
            prop_cases["INVENTED_CLAUSE"]["expected"] += 1
            _, recs2, _, _ = verify_commercial_grounding("Under Section 99.9, party shall forfeit all rights.", mock_retrieved)
            p2 = recs2[0].get("failure_mode", "UNKNOWN") if recs2 else "UNKNOWN"
            if p2 == "INVENTED_CLAUSE":
                prop_cases["INVENTED_CLAUSE"]["correct"] += 1
            else:
                failures_log.append({"family_id": fam_id, "type": "PROP_NOT_INVENTED", "details": f"Expected INVENTED_CLAUSE, got {p2}"})

            # 3. DIVERGENT_TERM case
            if "net_days" in test_cl.structured_slots:
                actual_days = test_cl.structured_slots["net_days"]
                val = actual_days.get("value") if isinstance(actual_days, dict) else actual_days
                divergent_draft = f"Pursuant to {test_cl.section}, Customer shall pay Net {val + 45} days."
            elif "cap_amount" in test_cl.structured_slots:
                divergent_draft = f"Pursuant to {test_cl.section}, liability is capped at $999,999,999."
            elif "uptime_pct" in test_cl.structured_slots:
                divergent_draft = f"Pursuant to {test_cl.section}, Vendor guarantees 95.0% uptime."
            else:
                divergent_draft = f"Pursuant to {test_cl.section}, Customer shall pay Net 120 days."

            prop_cases["DIVERGENT_TERM"]["expected"] += 1
            _, recs3, _, _ = verify_commercial_grounding(divergent_draft, mock_retrieved)
            p3 = recs3[0].get("failure_mode", "UNKNOWN") if recs3 else "UNKNOWN"
            if p3 == "DIVERGENT_TERM":
                prop_cases["DIVERGENT_TERM"]["correct"] += 1
            else:
                failures_log.append({"family_id": fam_id, "type": "PROP_NOT_DIVERGENT", "details": f"Expected DIVERGENT_TERM, got {p3}"})

            # 4. SUPERSEDED_TERM case
            mock_superseded = [{
                "section": test_cl.section,
                "title": test_cl.title,
                "content": test_cl.content,
                "structured_slots": test_cl.structured_slots,
                "superseded": True,
                "terminated": True,
                "superseded_by": "Restated Agreement"
            }]
            prop_cases["SUPERSEDED_TERM"]["expected"] += 1
            _, recs4, _, _ = verify_commercial_grounding(f"Under {test_cl.section}, term is operative.", mock_superseded)
            p4 = recs4[0].get("failure_mode", "UNKNOWN") if recs4 else "UNKNOWN"
            if p4 == "SUPERSEDED_TERM":
                prop_cases["SUPERSEDED_TERM"]["correct"] += 1
            else:
                failures_log.append({"family_id": fam_id, "type": "PROP_NOT_SUPERSEDED", "details": f"Expected SUPERSEDED_TERM, got {p4}"})

        family_results.append({
            "family_id": fam_id,
            "name": fam_name,
            "documents_count": len(docs),
            "relations_expected": len(expected_relations),
            "relations_tp": fam_tp,
            "relations_fp": fam_fp,
            "relations_fn": fam_fn,
            "queries_total": len(test_queries),
            "queries_correct": fam_queries_correct,
            "slots_total": fam_slots_total,
            "slots_matched": fam_slots_matched
        })
        db.close()

    elapsed = time.perf_counter() - t_start

    # Final Metric Calculations
    precision = (rel_tp / (rel_tp + rel_fp)) if (rel_tp + rel_fp) > 0 else 1.0
    recall = (rel_tp / (rel_tp + rel_fn)) if (rel_tp + rel_fn) > 0 else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    controlling_acc = (temporal_queries_correct / temporal_queries_total * 100.0) if temporal_queries_total > 0 else 100.0
    slot_acc = (slots_matched / slots_total * 100.0) if slots_total > 0 else 100.0

    total_prop_exp = sum(v["expected"] for v in prop_cases.values())
    total_prop_corr = sum(v["correct"] for v in prop_cases.values())
    prop_acc = (total_prop_corr / total_prop_exp * 100.0) if total_prop_exp > 0 else 100.0

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 3),
        "total_families": len(families),
        "metrics": {
            "relation_extraction": {
                "precision": round(precision * 100.0, 2),
                "recall": round(recall * 100.0, 2),
                "f1": round(f1 * 100.0, 2),
                "true_positives": rel_tp,
                "false_positives": rel_fp,
                "false_negatives": rel_fn
            },
            "controlling_clause_accuracy_as_of_date": {
                "accuracy_pct": round(controlling_acc, 2),
                "total_queries": temporal_queries_total,
                "correct_queries": temporal_queries_correct
            },
            "slot_exact_match": {
                "accuracy_pct": round(slot_acc, 2),
                "total_slots": slots_total,
                "matched_slots": slots_matched
            },
            "proposition_classification": {
                "accuracy_pct": round(prop_acc, 2),
                "total_cases": total_prop_exp,
                "correct_cases": total_prop_corr,
                "confusion_matrix": prop_cases
            }
        },
        "families": family_results,
        "failures": failures_log
    }

    if verbose:
        print("\n" + "=" * 80)
        print("  KRUSCHBIZ ADVERSARIAL MULTI-DOCUMENT SCORECARD")
        print("=" * 80)
        print(f"Total Families Evaluated: {len(families)}")
        print(f"Evaluation Duration:      {round(elapsed, 2)}s\n")
        print(f"1. Relation Extraction F1:           {summary['metrics']['relation_extraction']['f1']}% (P={summary['metrics']['relation_extraction']['precision']}%, R={summary['metrics']['relation_extraction']['recall']}%)")
        print(f"2. Controlling Clause Accuracy:      {summary['metrics']['controlling_clause_accuracy_as_of_date']['accuracy_pct']}% ({temporal_queries_correct}/{temporal_queries_total})")
        print(f"3. Slot Exact-Match Accuracy:        {summary['metrics']['slot_exact_match']['accuracy_pct']}% ({slots_matched}/{slots_total})")
        print(f"4. Proposition Grounding Accuracy:   {summary['metrics']['proposition_classification']['accuracy_pct']}% ({total_prop_corr}/{total_prop_exp})")
        print("-" * 80)
        print("Failures Published:")
        if failures_log:
            for f_item in failures_log:
                print(f"  ❌ [{f_item['family_id']}] {f_item['type']}: {f_item['details']}")
        else:
            print("  ✅ ZERO FAILURES across all 7 adversarial multi-document families.")
        print("=" * 80 + "\n")

    if output_json_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adversarial Multi-Document Evaluation Runner")
    parser.add_argument("--corpus", default=os.path.join(PROJECT_ROOT, "data/eval/adversarial_corpus.json"), help="Path to adversarial corpus JSON fixture")
    parser.add_argument("--output", default=os.path.join(PROJECT_ROOT, "data/eval/adversarial_eval_results.json"), help="Path to write JSON results")
    args = parser.parse_args()

    results = run_adversarial_eval(corpus_path=args.corpus, output_json_path=args.output)
    metrics = results["metrics"]

    # Minimum Production Thresholds
    assert metrics["relation_extraction"]["f1"] >= 80.0, f"Relation F1 below threshold: {metrics['relation_extraction']['f1']}%"
    assert metrics["controlling_clause_accuracy_as_of_date"]["accuracy_pct"] >= 95.0, f"Controlling clause accuracy below threshold: {metrics['controlling_clause_accuracy_as_of_date']['accuracy_pct']}%"
    assert metrics["slot_exact_match"]["accuracy_pct"] >= 95.0, f"Slot exact-match below threshold: {metrics['slot_exact_match']['accuracy_pct']}%"
    assert metrics["proposition_classification"]["accuracy_pct"] >= 95.0, f"Proposition classification below threshold: {metrics['proposition_classification']['accuracy_pct']}%"
    sys.exit(0)
