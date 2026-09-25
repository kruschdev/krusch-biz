#!/usr/bin/env python3
"""
scripts/eval_contract_vs_statute_join.py
========================================
1-Command Cross-Engine Compliance Evaluation Benchmark:
"The Contract-vs-Statute Join Engine (`POST /conflicts/contract-vs-statute`)"

Evaluates 11 end-to-end conflict test pairs comparing commercial and residential
contract slots against California statutory ceilings, floors, and non-waivable doctrines
under varying historical `as_of_date` milestones:
  1. AB 12 Post-Enactment Security Deposit Violation (2.0 months demanded post-2024-07-01 -> VOID)
  2. AB 12 Pre-Enactment Security Deposit Compliance (2.0 months demanded pre-2024-07-01 -> ENFORCEABLE)
  3. Sub-Statutory Landlord Entry Notice (12 hrs vs 24 hr § 1954 floor -> VOID)
  4. More Generous Landlord Entry Notice (48 hrs vs 24 hr § 1954 floor -> MORE_GENEROUS / ENFORCEABLE)
  5. Extended Security Deposit Return Timeline (45 days vs 21-day § 1950.5(g) ceiling -> VOID)
  6. Expedited Security Deposit Return Timeline (14 days vs 21-day § 1950.5(g) ceiling -> MORE_GENEROUS)
  7. Prohibited Habitability & Repair-and-Deduct Waiver (§ 1942.1 public policy violation -> VOID)
  8. Prohibited Retaliation Defense Waiver (§ 1942.5(h) public policy violation -> VOID)
  9. Excessive Late Payment Fee / Liquidated Damages (15% vs 5% § 1671(d) ceiling -> VOID)
 10. Commercial Lease Security Deposit Freedom of Contract (§ 1950.7(f) flexibility -> ENFORCEABLE)
 11. Untracked Topic Coverage Gap Detection (Unknown topic -> COVERAGE_GAP)

Runs completely self-contained in <1 second with zero external dependencies.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.backend.db as db_mod
from src.backend.compliance import (
    ContractVsStatuteRequest,
    evaluate_contract_vs_statute,
)
from src.backend.db import (
    Agreement,
    Clause,
    init_db,
)

# ANSI Styling
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def seed_benchmark_corpus(db) -> None:
    """Seed test agreements and clauses covering all 11 evaluation scenarios."""
    # 1. Residential Lease 2024 (Post-AB 12 with non-compliant deposit, entry notice, and waiver)
    lease_post = Agreement(
        tenant_id="org_benchmark",
        title="Highland Residential Lease Agreement (2024)",
        instrument_type="lease",
        counterparty="Highland Residential LLC",
        effective_date=datetime(2024, 8, 1),
        execution_status="executed",
        status="active"
    )
    db.add(lease_post)
    db.flush()

    c1 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_post.id,
        section="Section 3.1",
        title="Security Deposit",
        topic="SECURITY_DEPOSIT",
        authority_class="governing_agreement",
        content="Tenant shall deposit an amount equal to two (2) months rent ($5,000) as security.",
        structured_slots={"deposit_cap_months": 2.0},
        is_active=True
    )
    c2 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_post.id,
        section="Section 8.2",
        title="Right of Entry",
        topic="ENTRY_NOTICE",
        authority_class="governing_agreement",
        content="Landlord may enter premises upon twelve (12) hours advance verbal or written notice.",
        structured_slots={"entry_notice_hours": 12.0},
        is_active=True
    )
    c3 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_post.id,
        section="Section 3.4",
        title="Deposit Return Accounting",
        topic="DEPOSIT_RETURN",
        authority_class="governing_agreement",
        content="Landlord shall have forty-five (45) calendar days after surrender to return unused deposit.",
        structured_slots={"deposit_return_days": 45.0},
        is_active=True
    )
    c4 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_post.id,
        section="Section 14.1",
        title="As-Is Condition & Habitability Disclaimer",
        topic="HABITABILITY_WAIVER",
        authority_class="governing_agreement",
        content="Tenant accepts premises strictly as-is and waives all statutory rights under Civil Code Section 1941 and 1942 to repair and deduct.",
        structured_slots={"waives_habitability": True, "waives_repair_deduct": True},
        is_active=True
    )
    c5 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_post.id,
        section="Section 19.3",
        title="Waiver of Retaliation Defenses",
        topic="RETALIATION_WAIVER",
        authority_class="governing_agreement",
        content="Tenant covenants that it waives any right to assert retaliatory eviction defenses under Section 1942.5.",
        structured_slots={"waives_retaliation_defense": True},
        is_active=True
    )
    c6 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_post.id,
        section="Section 4.2",
        title="Late Charge",
        topic="LATE_FEE",
        authority_class="governing_agreement",
        content="A late fee of fifteen percent (15%) shall be assessed for any rent paid after the 3rd.",
        structured_slots={"late_penalty_pct": 15.0},
        is_active=True
    )

    # 2. Historical Pre-AB 12 Residential Lease (Executed 2024-03-01)
    lease_pre = Agreement(
        tenant_id="org_benchmark",
        title="Oakland Historical Apartment Lease (Early 2024)",
        instrument_type="lease",
        counterparty="Heritage Rentals Inc",
        effective_date=datetime(2024, 3, 1),
        execution_status="executed",
        status="active"
    )
    db.add(lease_pre)
    db.flush()

    c7 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_pre.id,
        section="Section 3.1",
        title="Security Deposit",
        topic="SECURITY_DEPOSIT",
        authority_class="governing_agreement",
        content="Tenant shall pay two (2) months rent as security deposit upon signing.",
        structured_slots={"deposit_cap_months": 2.0},
        is_active=True
    )

    # 3. Model Protective Residential Lease (Generous notice and return timelines)
    lease_model = Agreement(
        tenant_id="org_benchmark",
        title="Civic Gold Standard Residential Lease",
        instrument_type="lease",
        counterparty="Civic Housing Trust",
        effective_date=datetime(2024, 8, 1),
        execution_status="executed",
        status="active"
    )
    db.add(lease_model)
    db.flush()

    c8 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_model.id,
        section="Section 7.1",
        title="Landlord Entry Notice",
        topic="ENTRY_NOTICE",
        authority_class="governing_agreement",
        content="Landlord shall provide at least forty-eight (48) hours advance written notice prior to entering.",
        structured_slots={"entry_notice_hours": 48.0},
        is_active=True
    )
    c9 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_model.id,
        section="Section 4.1",
        title="Expedited Deposit Refund",
        topic="DEPOSIT_RETURN",
        authority_class="governing_agreement",
        content="Landlord guarantees itemized accounting and return of deposit within fourteen (14) calendar days.",
        structured_slots={"deposit_return_days": 14.0},
        is_active=True
    )

    # 4. Commercial Real Estate Lease (Warehouse & Office)
    lease_comm = Agreement(
        tenant_id="org_benchmark",
        title="Port of Oakland Industrial Warehouse Lease",
        instrument_type="commercial_lease",
        counterparty="Bayside Logistics Partners LP",
        effective_date=datetime(2024, 8, 1),
        execution_status="executed",
        status="active"
    )
    db.add(lease_comm)
    db.flush()

    c10 = Clause(
        tenant_id="org_benchmark",
        agreement_id=lease_comm.id,
        section="Section 5.1",
        title="Security Deposit",
        topic="COMMERCIAL_SECURITY_DEPOSIT",
        authority_class="governing_agreement",
        content="Tenant shall deposit an amount equal to three (3) months base rent ($24,000) pursuant to Civil Code Section 1950.7.",
        structured_slots={"deposit_cap_months": 3.0},
        is_active=True
    )

    db.add_all([c1, c2, c3, c4, c5, c6, c7, c8, c9, c10])
    db.commit()


# Benchmark test pairs specification
BENCHMARK_CASES: List[Dict[str, Any]] = [
    {
        "id": "TC-01",
        "name": "AB 12 Post-Enactment Deposit Violation",
        "counterparty": "Highland Residential LLC",
        "topic": "SECURITY_DEPOSIT",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_less_than_mandatory",
        "expected_enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
        "expected_citation": "1950.5",
        "expected_verdict": "NON_COMPLIANT_TERMS_FOUND"
    },
    {
        "id": "TC-02",
        "name": "AB 12 Pre-Enactment Deposit Compliance",
        "counterparty": "Heritage Rentals Inc",
        "topic": "SECURITY_DEPOSIT",
        "as_of_date": "2024-04-01",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "aligned",
        "expected_enforceability": "ENFORCEABLE",
        "expected_citation": "1950.5",
        "expected_verdict": "COMPLIANT"
    },
    {
        "id": "TC-03",
        "name": "Sub-Statutory Entry Notice (12h vs 24h floor)",
        "counterparty": "Highland Residential LLC",
        "topic": "ENTRY_NOTICE",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_less_than_mandatory",
        "expected_enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
        "expected_citation": "1954",
        "expected_verdict": "NON_COMPLIANT_TERMS_FOUND"
    },
    {
        "id": "TC-04",
        "name": "More Generous Entry Notice (48h vs 24h floor)",
        "counterparty": "Civic Housing Trust",
        "topic": "ENTRY_NOTICE",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_more_generous",
        "expected_enforceability": "ENFORCEABLE",
        "expected_citation": "1954",
        "expected_verdict": "COMPLIANT"
    },
    {
        "id": "TC-05",
        "name": "Deposit Return Timeline Extended (45d vs 21d)",
        "counterparty": "Highland Residential LLC",
        "topic": "DEPOSIT_RETURN",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_less_than_mandatory",
        "expected_enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
        "expected_citation": "1950.5",
        "expected_verdict": "NON_COMPLIANT_TERMS_FOUND"
    },
    {
        "id": "TC-06",
        "name": "Deposit Return Timeline Expedited (14d vs 21d)",
        "counterparty": "Civic Housing Trust",
        "topic": "DEPOSIT_RETURN",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_more_generous",
        "expected_enforceability": "ENFORCEABLE",
        "expected_citation": "1950.5",
        "expected_verdict": "COMPLIANT"
    },
    {
        "id": "TC-07",
        "name": "Habitability / Repair-and-Deduct Waiver",
        "counterparty": "Highland Residential LLC",
        "topic": "HABITABILITY_WAIVER",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_less_than_mandatory",
        "expected_enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
        "expected_citation": "1942.1",
        "expected_verdict": "NON_COMPLIANT_TERMS_FOUND"
    },
    {
        "id": "TC-08",
        "name": "Retaliation Defense Waiver (§ 1942.5(h))",
        "counterparty": "Highland Residential LLC",
        "topic": "RETALIATION_WAIVER",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_less_than_mandatory",
        "expected_enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
        "expected_citation": "1942.5",
        "expected_verdict": "NON_COMPLIANT_TERMS_FOUND"
    },
    {
        "id": "TC-09",
        "name": "Excessive Late Fee Liquidated Damages (15% vs 5%)",
        "counterparty": "Highland Residential LLC",
        "topic": "LATE_FEE",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "contract_less_than_mandatory",
        "expected_enforceability": "VOID_AS_AGAINST_PUBLIC_POLICY",
        "expected_citation": "1671",
        "expected_verdict": "NON_COMPLIANT_TERMS_FOUND"
    },
    {
        "id": "TC-10",
        "name": "Commercial Tenancy Deposit Flexibility (3.0 mo)",
        "counterparty": "Bayside Logistics Partners LP",
        "topic": "COMMERCIAL_SECURITY_DEPOSIT",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "commercial",
        "expected_alignment": "aligned",
        "expected_enforceability": "ENFORCEABLE",
        "expected_citation": "1950.7",
        "expected_verdict": "COMPLIANT"
    },
    {
        "id": "TC-11",
        "name": "Untracked Statutory Topic Coverage Gap",
        "counterparty": "Highland Residential LLC",
        "topic": "MUNICIPAL_SIDEWALK_SWEEPING",
        "as_of_date": "2024-08-15",
        "jurisdiction": "CA:Oakland",
        "property_type": "residential",
        "expected_alignment": "coverage_gap",
        "expected_enforceability": "UNSPECIFIED",
        "expected_citation": None,
        "expected_verdict": "COVERAGE_GAPS_IDENTIFIED"
    }
]


def run_benchmark() -> bool:
    """Execute the full 1-command benchmark and print formatted diagnostic scorecard."""
    print(f"\n{BOLD}{CYAN}{'='*80}{RESET}")
    print(f"{BOLD}{CYAN} KRUSCHBIZ x KRUSCHLAW: THE JOIN COMPLIANCE BENCHMARK{RESET}")
    print(f"{DIM} Authoritative Contract-vs-Statute Verification Engine (`POST /conflicts/contract-vs-statute`){RESET}")
    print(f"{BOLD}{CYAN}{'='*80}{RESET}\n")

    # In-memory database setup
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Session = sessionmaker(bind=engine)
    db_mod.engine = engine
    db_mod.SessionLocal = Session
    init_db(engine)

    db = Session()
    try:
        seed_benchmark_corpus(db)
        print(f" {GREEN}✓{RESET} Benchmark test corpus seeded in SQLite memory ({len(BENCHMARK_CASES)} cases)\n")

        all_passed = True
        total_time_ms = 0.0

        print(f" {'ID':<6} | {'Scenario Name':<42} | {'Alignment':<26} | {'Verdict':<12} | {'Latency':<8}")
        print(f" {'-'*6}-+-{'-'*42}-+-{'-'*26}-+-{'-'*12}-+-{'-'*8}")

        for tc in BENCHMARK_CASES:
            t0 = time.perf_counter()
            req = ContractVsStatuteRequest(
                counterparty=tc["counterparty"],
                jurisdiction=tc["jurisdiction"],
                as_of_date=tc["as_of_date"],
                topics=[tc["topic"]],
                property_type=tc.get("property_type", "residential")
            )
            res = evaluate_contract_vs_statute(
                db_biz=db,
                request=req,
                tenant_id="org_benchmark"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            total_time_ms += elapsed_ms

            f = res.findings[0]
            actual_alignment = f.alignment
            actual_enforceability = f.enforceability
            actual_verdict = res.verdict
            citation = f.controlling_statute.get("citation", "") if f.controlling_statute else ""

            # Check correctness
            match_align = (actual_alignment == tc["expected_alignment"])
            match_enf = (actual_enforceability == tc["expected_enforceability"])
            match_cite = (tc["expected_citation"] is None or tc["expected_citation"] in citation)
            match_verdict = (actual_verdict == tc["expected_verdict"])

            passed = match_align and match_enf and match_cite and match_verdict
            if not passed:
                all_passed = False

            status_str = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
            print(f" {tc['id']:<6} | {tc['name']:<42} | {actual_alignment:<26} | {status_str:<12} | {elapsed_ms:>6.2f}ms")

            if not passed:
                print(f"   {RED}↳ MISMATCH:{RESET} Expected align={tc['expected_alignment']}, got {actual_alignment}")
                print(f"   {RED}↳ DETAILS:{RESET} Expected enf={tc['expected_enforceability']}, got {actual_enforceability}")
                print(f"   {RED}↳ CITATION:{RESET} Expected '{tc['expected_citation']}' in '{citation}'")

        print(f"\n{BOLD}{CYAN}{'='*80}{RESET}")
        avg_ms = total_time_ms / len(BENCHMARK_CASES)
        score_pct = (sum(1 for _ in BENCHMARK_CASES if all_passed) / len(BENCHMARK_CASES)) * 100.0 if all_passed else 0.0

        if all_passed:
            print(f" {BOLD}{GREEN}ALL {len(BENCHMARK_CASES)}/{len(BENCHMARK_CASES)} BENCHMARK PAIRS PASSED ({score_pct:.1f}% CONVERGENCE){RESET}")
            print(f" {DIM}Total Execution Time: {total_time_ms:.2f}ms (Average Latency: {avg_ms:.2f}ms/join){RESET}")
            print(f"{BOLD}{CYAN}{'='*80}{RESET}\n")
            return True
        else:
            print(f" {BOLD}{RED}BENCHMARK SUITE FAILED CONVERGENCE GATE{RESET}")
            print(f"{BOLD}{CYAN}{'='*80}{RESET}\n")
            return False

    finally:
        db.close()


if __name__ == "__main__":
    success = run_benchmark()
    sys.exit(0 if success else 1)
