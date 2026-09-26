#!/usr/bin/env python3
"""
scripts/demo_60s.py
===================
60-Second Headless Demonstration of KruschBiz.
Runs with zero external dependencies (no Ollama, no PostgreSQL, no GPU).
Demonstrates:
  1. DAG Precedence Resolver walking confirmed agreement graph
  2. Authority Extraction: Structured Commercial Slots (Net 30, Carve-Outs)
  3. Proposition Grounding Scanner with exact-slot verification and failure code detection
"""

import os
import sys
import time
from datetime import date

# Set headless flags before importing backend
os.environ["HEADLESS_MODE"] = "1"
os.environ["USE_MOCK_EMBEDDINGS"] = "1"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.db import SessionLocal, init_db, engine
from src.backend.resolver import resolve_controlling_clause
from src.backend.rag import verify_commercial_grounding


def main():
    t0 = time.perf_counter()
    print("\n" + "=" * 76)
    print("  💼 KRUSCHBIZ 60-SECOND HEADLESS DEMO")
    print("  Deterministic Contract Precedence & Slot Grounding Engine")
    print("=" * 76 + "\n")

    init_db(engine)
    db = SessionLocal()

    tenant_id = "org_default"
    counterparty = "CloudScale AI"
    as_of = date(2025, 6, 1)

    print("Step 1: Inspecting Precedence Resolution on Confirmed Contract Graph")
    print("-" * 76)

    # 1. Resolve Payment Terms
    res_pay = resolve_controlling_clause(
        db=db,
        tenant_id=tenant_id,
        counterparty=counterparty,
        topic="PAYMENT_TERMS",
        as_of_date=as_of
    )
    cc_pay = res_pay.get("controlling_clause") or {}
    print(f"  [Topic: PAYMENT_TERMS] As-of: {as_of}")
    print(f"  -> Controlling Instrument: {cc_pay.get('agreement_title')}")
    print(f"  -> Section: {cc_pay.get('section')} | Net Days: {cc_pay.get('structured_slots', {}).get('net_days', {}).get('value')} days")
    print(f"  -> Precedence Rationale:   {res_pay.get('resolution_rationale')}")

    # 2. Resolve Limitation of Liability & Carve-Outs
    res_liab = resolve_controlling_clause(
        db=db,
        tenant_id=tenant_id,
        counterparty=counterparty,
        topic="LIMITATION_OF_LIABILITY",
        as_of_date=as_of
    )
    cc_liab = res_liab.get("controlling_clause") or {}
    carve_outs = cc_liab.get("structured_slots", {}).get("carve_outs", {}).get("value", [])
    print(f"\n  [Topic: LIMITATION_OF_LIABILITY] As-of: {as_of}")
    print(f"  -> Controlling Instrument: {cc_liab.get('agreement_title')}")
    print(f"  -> Section: {cc_liab.get('section')} | Capped: {cc_liab.get('structured_slots', {}).get('capped', {}).get('value')}")
    print(f"  -> Express Carve-Outs:     {', '.join(carve_outs)}")

    print("\n" + "=" * 76)
    print("Step 2: Auditing AI-Generated Commercial Claims Against Controlling Clauses")
    print("-" * 76)

    # Proposition A: Grounded Truth (Matches Net 30 under Section 4.2)
    claim_a = "Under Section 4.2, payment is Net 30 days."
    is_grounded_a, audit_a, status_a, _ = verify_commercial_grounding(
        analysis_text=claim_a,
        retrieved_clauses=[cc_pay],
        controlling_result=res_pay
    )
    print(f"\n  Claim A: \"{claim_a}\"")
    print(f"  -> Grounded:           ✅ {is_grounded_a}")
    print(f"  -> Claim Status:       {audit_a[0].get('status') if audit_a else 'N/A'}")
    print(f"  -> Supporting Clause:  {audit_a[0].get('cited_authority') if audit_a else 'N/A'}")

    # Proposition B: Divergent / Hallucinated Slot (Net 60 claimed, Net 30 governing)
    claim_b = "Under Section 4.2, payment is Net 60 days."
    is_grounded_b, audit_b, status_b, _ = verify_commercial_grounding(
        analysis_text=claim_b,
        retrieved_clauses=[cc_pay],
        controlling_result=res_pay
    )
    fail_mode_b = audit_b[0].get("failure_mode") if audit_b else "UNKNOWN"
    details_b = audit_b[0].get("details") if audit_b else ""
    print(f"\n  Claim B: \"{claim_b}\"")
    print(f"  -> Grounded:           ❌ {is_grounded_b}")
    print(f"  -> Failure Code:       {fail_mode_b}")
    print(f"  -> Diagnostics:        {details_b}")

    # Proposition C: Citation of Non-Existent Authority (Hallucinated Section)
    claim_c = "Under Section 99.1, payments are due Net 30 days."
    is_grounded_c, audit_c, status_c, _ = verify_commercial_grounding(
        analysis_text=claim_c,
        retrieved_clauses=[cc_pay],
        controlling_result=res_pay
    )
    fail_mode_c = audit_c[0].get("failure_mode") if audit_c else "UNKNOWN"
    details_c = audit_c[0].get("details") if audit_c else ""
    print(f"\n  Claim C: \"{claim_c}\"")
    print(f"  -> Grounded:           ❌ {is_grounded_c}")
    print(f"  -> Failure Code:       {fail_mode_c}")
    print(f"  -> Diagnostics:        {details_c}")

    db.close()
    elapsed = time.perf_counter() - t0
    print("\n" + "=" * 76)
    print(f"  ✅ DEMO COMPLETED IN {elapsed:.3f}s (Zero Cloud I/O, Zero External Dependencies)")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    main()
