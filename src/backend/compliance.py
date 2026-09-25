"""
src/backend/compliance.py
=========================
The Contract-vs-Statute Join Engine (`POST /conflicts/contract-vs-statute`).
Compares controlling contract clause slots (resolved via KruschBiz DAG)
against mandatory statutory ceilings and floors (resolved via KruschLaw Precedence Graph).

Deterministic slot evaluation over LLM similarity:
  - 'aligned': Contract complies with statutory floor/ceiling.
  - 'contract_more_generous': Contract grants more rights than statutory floor (e.g. 48hr vs 24hr notice).
  - 'contract_less_than_mandatory': Contract violates non-waivable statute (e.g. demanding 2 months deposit when statute caps at 1 month).
  - 'coverage_gap': Statutory rule or contract clause absent from record.
  - 'jurisdiction_mismatch': Contract attempts to contract out of non-waivable local protections.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .db import DealMatter
from .resolver import resolve_controlling_clause, to_utc_date

logger = logging.getLogger("kruschbiz.compliance")


# ---------------------------------------------------------------------------
# STATUTORY MANDATES REGISTRY (California & Municipal Baselines)
# ---------------------------------------------------------------------------

STATUTORY_MANDATES: dict[str, dict[str, Any]] = {
    "SECURITY_DEPOSIT": {
        "citation": "Cal. Civ. Code § 1950.5(c)(1)",
        "mandate_type": "STATUTORY_CEILING",
        "pre_ab12_ceiling": 2.0,      # Prior to July 1, 2024: 2 months unfurnished rent
        "post_ab12_ceiling": 1.0,     # On or after July 1, 2024 (AB 12): 1 month rent
        "ab12_effective_date": date(2024, 7, 1),
        "slot_key": "deposit_cap_months",
        "unit": "months_rent",
        "statutory_text": "A landlord may not demand or receive security in an amount exceeding one month's rent (AB 12, effective July 1, 2024).",
        "non_waivable": True,
    },
    "ENTRY_NOTICE": {
        "citation": "Cal. Civ. Code § 1954(d)(1)",
        "mandate_type": "STATUTORY_FLOOR",
        "minimum_hours": 24.0,        # 24 hours written notice minimum
        "slot_key": "entry_notice_hours",
        "unit": "hours",
        "statutory_text": "The landlord shall give the tenant reasonable written notice of the landlord's intent to enter, with 24 hours presumed reasonable.",
        "non_waivable": True,
    },
    "DEPOSIT_RETURN": {
        "citation": "Cal. Civ. Code § 1950.5(g)(1)",
        "mandate_type": "STATUTORY_CEILING",
        "max_return_days": 21.0,      # 21 calendar days ceiling
        "slot_key": "deposit_return_days",
        "unit": "calendar_days",
        "statutory_text": "No later than 21 calendar days after the tenant has vacated the premises, the landlord shall furnish a copy of an itemized statement along with the remaining portion of the security deposit.",
        "non_waivable": True,
    },
    "HABITABILITY_WAIVER": {
        "citation": "Cal. Civ. Code § 1942.1",
        "mandate_type": "STATUTORY_PROHIBITION",
        "slot_key": "waives_habitability",
        "unit": "prohibited_waiver",
        "statutory_text": "Any agreement by a tenant by which he waives or modifies his rights under Section 1941 or 1942 shall be void as contrary to public policy.",
        "non_waivable": True,
    },
    "REPAIR_AND_DEDUCT": {
        "citation": "Cal. Civ. Code § 1942.1",
        "mandate_type": "STATUTORY_PROHIBITION",
        "slot_key": "waives_repair_deduct",
        "unit": "prohibited_waiver",
        "statutory_text": "Any agreement by a tenant waiving repair-and-deduct remedies under Section 1942 shall be void as contrary to public policy.",
        "non_waivable": True,
    },
    "COMMERCIAL_SECURITY_DEPOSIT": {
        "citation": "Cal. Civ. Code § 1950.7(f)",
        "mandate_type": "STATUTORY_PERMISSIVE_WAIVER",
        "slot_key": "commercial_deposit_waiver",
        "unit": "permissive_waiver",
        "statutory_text": "In commercial leases, parties may contractually agree to terms different from Section 1950.7 or waive statutory deposit return provisions (Civ. Code § 1950.7(f)).",
        "non_waivable": False,
    },
    "RETALIATION_WAIVER": {
        "citation": "Cal. Civ. Code § 1942.5(h)",
        "mandate_type": "STATUTORY_PROHIBITION",
        "slot_key": "waives_retaliation_defense",
        "unit": "prohibited_waiver",
        "statutory_text": "Any waiver by a tenant of rights under Section 1942.5 shall be void as contrary to public policy.",
        "non_waivable": True,
    },
    "LATE_FEE": {
        "citation": "Cal. Civ. Code § 1671(d)",
        "mandate_type": "STATUTORY_CEILING",
        "max_penalty_pct": 5.0,       # Customary 5% liquidated damages ceiling
        "slot_key": "late_penalty_pct",
        "unit": "percent",
        "statutory_text": "Late fees must represent a reasonable endeavor to estimate fair average compensation for the loss sustained by late payment.",
        "non_waivable": True,
    },
    "PAYMENT_TERMS": {
        "citation": "Cal. Const. Art. XV § 1",
        "mandate_type": "STATUTORY_CEILING",
        "max_annual_interest_pct": 10.0,
        "slot_key": "late_interest_pct",
        "unit": "percent_per_annum",
        "statutory_text": "The maximum legal rate of interest for non-exempt commercial obligations is 10 percent per annum.",
        "non_waivable": True,
    }
}

TOPIC_ALIASES = {
    "DEPOSIT_RETURN_DAYS": "DEPOSIT_RETURN",
    "DEPOSIT_TIMELINE": "DEPOSIT_RETURN",
    "REPAIR_DEDUCT": "REPAIR_AND_DEDUCT",
    "HABITABILITY": "HABITABILITY_WAIVER",
    "USURY": "PAYMENT_TERMS",
    "INTEREST_RATE": "PAYMENT_TERMS",
    "COMMERCIAL_DEPOSIT": "COMMERCIAL_SECURITY_DEPOSIT",
}


# ---------------------------------------------------------------------------
# REQUEST / RESPONSE SCHEMAS
# ---------------------------------------------------------------------------

class ContractVsStatuteRequest(BaseModel):
    deal_id: Optional[int] = Field(None, description="Optional KruschBiz deal matter ID")
    matter_id: Optional[int] = Field(None, description="Optional KruschLaw legal matter ID")
    counterparty: Optional[str] = Field(None, description="Counterparty or tenant entity name")
    jurisdiction: str = Field("CA:Oakland", description="Jurisdiction code, e.g. 'CA:Oakland', 'California'")
    as_of_date: str = Field(..., description="Mandatory historical or evaluation date (YYYY-MM-DD). No silent 'today'.")
    topics: List[str] = Field(default_factory=lambda: ["SECURITY_DEPOSIT", "ENTRY_NOTICE", "LATE_FEE"], description="Topics to evaluate")
    property_type: Optional[str] = Field("residential", description="Property category: 'residential' or 'commercial'")


class ComplianceFinding(BaseModel):
    topic: str
    alignment: str                    # aligned, contract_more_generous, contract_less_than_mandatory, coverage_gap, jurisdiction_mismatch
    enforceability: str               # ENFORCEABLE, VOID_AS_AGAINST_PUBLIC_POLICY, PREEMPTED, UNSPECIFIED
    coverage: str = "partial"         # Invariant: Mark every finding coverage: partial unless jurisdiction is complete
    contract_clause: Optional[Dict[str, Any]] = None
    controlling_statute: Optional[Dict[str, Any]] = None
    explanation: str
    trace_id: str


class ContractVsStatuteResponse(BaseModel):
    verdict: str                      # COMPLIANT, NON_COMPLIANT_TERMS_FOUND, COVERAGE_GAPS_IDENTIFIED
    as_of_date: str
    jurisdiction: str
    counterparty: Optional[str] = None
    coverage_completeness: str = "partial"
    findings: List[ComplianceFinding]


# ---------------------------------------------------------------------------
# CORE JOIN EVALUATION ENGINE
# ---------------------------------------------------------------------------

def evaluate_contract_vs_statute(
    db_biz: Session,
    request: ContractVsStatuteRequest,
    tenant_id: str = "org_default",
    db_law: Optional[Any] = None
) -> ContractVsStatuteResponse:
    """
    Execute the authoritative Contract-vs-Statute Join pipeline:
      1. Enforce mandatory as_of_date (Invariant: NO SILENT 'TODAY').
      2. Resolve counterparty from deal_id if omitted.
      3. For each requested topic:
         a. Walk commercial contract graph in KruschBiz -> Controlling Clause.
         b. Walk statutory authority graph in KruschLaw -> Controlling Statute.
         c. Deterministically evaluate slot alignment against mandatory ceilings/floors.
      4. Synthesize overall portfolio verdict.
    """
    # 1. Enforce mandatory as_of_date
    if not request.as_of_date or not request.as_of_date.strip():
        raise ValueError("Non-negotiable Invariant: 'as_of_date' is mandatory. No silent 'today' is permitted.")

    as_of = to_utc_date(request.as_of_date)

    # 2. Resolve counterparty
    counterparty = request.counterparty
    if not counterparty and request.deal_id:
        deal = db_biz.query(DealMatter).filter(
            DealMatter.id == request.deal_id,
            DealMatter.tenant_id == tenant_id
        ).first()
        if deal:
            counterparty = deal.counterparty_name

    counterparty_query = counterparty or "Default Entity"

    # 3. Parse jurisdiction
    city = None
    _state = "CA"
    if ":" in request.jurisdiction:
        parts = request.jurisdiction.split(":", 1)
        _state = parts[0].strip()
        city = parts[1].strip()
    elif "Oakland" in request.jurisdiction:
        city = "Oakland"

    findings: List[ComplianceFinding] = []
    has_non_compliant = False
    has_coverage_gap = False

    for topic in request.topics:
        topic_norm = topic.strip().upper()
        topic_norm = TOPIC_ALIASES.get(topic_norm, topic_norm)
        trace_id = f"trace_join_{uuid.uuid4().hex[:12]}"

        # Step A: Resolve Commercial Clause via KruschBiz DAG
        biz_res = resolve_controlling_clause(
            db=db_biz,
            tenant_id=tenant_id,
            counterparty=counterparty_query,
            topic=topic_norm,
            as_of_date=as_of
        )

        winning_clause = biz_res.get("controlling_clause")
        contract_clause_info = None
        contract_slots = {}
        if winning_clause:
            contract_slots = dict(winning_clause.get("structured_slots") or {})
            contract_clause_info = {
                "instrument": winning_clause.get("agreement_title"),
                "section": winning_clause.get("section"),
                "span": winning_clause.get("content"),
                "normalized_slot": contract_slots,
                "authority_class": winning_clause.get("authority_class")
            }

        # Step B: Resolve Statutory Mandate via KruschLaw
        statute_info = None
        statutory_mandate = STATUTORY_MANDATES.get(topic_norm)

        # Attempt dynamic KruschLaw resolution if available
        dynamic_law_res = None
        try:
            # Check if krusch-law is on path
            from src.backend.resolver import resolve_controlling_law as law_resolver
            dynamic_law_res = law_resolver(
                doctrine_or_topic=topic_norm.replace("_", " "),
                city=city,
                as_of_date=as_of,
                db=db_law
            )
        except Exception as exc:
            logger.debug(f"Direct KruschLaw dynamic resolver call skipped ({exc}). Using statutory mandates registry.")

        if dynamic_law_res and getattr(dynamic_law_res, "controlling_node", None):
            node = dynamic_law_res.controlling_node
            statute_info = {
                "citation": getattr(dynamic_law_res, "governing_citation", "Statute"),
                "effective_date": str(node.get("effective_date", "2024-01-01")),
                "mandate_type": "STATUTORY_CEILING" if "ceiling" in topic_norm.lower() or "deposit" in topic_norm.lower() else "STATUTORY_FLOOR",
                "span": node.get("content", ""),
                "normalized_slot": getattr(dynamic_law_res, "statutory_slots", {})
            }
        elif statutory_mandate:
            # Determine temporal ceiling based on as_of_date
            mandate_slots = {}
            if topic_norm == "SECURITY_DEPOSIT":
                eff = statutory_mandate["ab12_effective_date"]
                cap = statutory_mandate["post_ab12_ceiling"] if as_of >= eff else statutory_mandate["pre_ab12_ceiling"]
                mandate_slots["deposit_cap_months"] = cap
                mandate_slots["max_months"] = cap
            elif topic_norm == "ENTRY_NOTICE":
                mandate_slots["entry_notice_hours"] = statutory_mandate["minimum_hours"]
                mandate_slots["min_hours"] = statutory_mandate["minimum_hours"]
            elif topic_norm == "DEPOSIT_RETURN":
                mandate_slots["deposit_return_days"] = statutory_mandate["max_return_days"]
                mandate_slots["max_days"] = statutory_mandate["max_return_days"]
            elif topic_norm in ("HABITABILITY_WAIVER", "REPAIR_AND_DEDUCT"):
                mandate_slots["waiver_prohibited"] = True
                mandate_slots["statute_voids_waiver"] = True
            elif topic_norm == "COMMERCIAL_SECURITY_DEPOSIT":
                mandate_slots["waiver_permitted"] = True
                mandate_slots["freedom_of_contract"] = True
            elif topic_norm == "RETALIATION_WAIVER":
                mandate_slots["waiver_prohibited"] = True
                mandate_slots["statute_voids_waiver"] = True
            elif topic_norm in ("LATE_FEE", "PAYMENT_TERMS"):
                pct = statutory_mandate.get("max_penalty_pct") or statutory_mandate.get("max_annual_interest_pct", 10.0)
                mandate_slots["max_pct"] = pct

            statute_info = {
                "citation": statutory_mandate["citation"],
                "effective_date": "2024-07-01" if (topic_norm == "SECURITY_DEPOSIT" and as_of >= date(2024, 7, 1)) else "2020-01-01",
                "mandate_type": statutory_mandate["mandate_type"],
                "span": statutory_mandate["statutory_text"],
                "normalized_slot": mandate_slots
            }

        # Step C: Deterministic Evaluation & Slot Comparison
        if not winning_clause and not statute_info:
            findings.append(ComplianceFinding(
                topic=topic_norm,
                alignment="coverage_gap",
                enforceability="UNSPECIFIED",
                contract_clause=None,
                controlling_statute=None,
                explanation=f"Topic '{topic_norm}' not found in contract portfolio nor recognized statutory registry.",
                trace_id=trace_id
            ))
            has_coverage_gap = True
            continue

        if not winning_clause:
            findings.append(ComplianceFinding(
                topic=topic_norm,
                alignment="coverage_gap",
                enforceability="UNSPECIFIED",
                contract_clause=None,
                controlling_statute=statute_info,
                explanation=f"Mandatory statute '{statute_info.get('citation')}' exists, but no operative contract clause was found in portfolio.",
                trace_id=trace_id
            ))
            has_coverage_gap = True
            continue

        if not statute_info:
            findings.append(ComplianceFinding(
                topic=topic_norm,
                alignment="aligned",
                enforceability="ENFORCEABLE",
                contract_clause=contract_clause_info,
                controlling_statute=None,
                explanation=f"Contract terms govern; no preemptive statutory mandate found for '{topic_norm}'.",
                trace_id=trace_id
            ))
            continue

        # Deterministic slot comparisons:
        alignment = "aligned"
        enforceability = "ENFORCEABLE"
        explanation = f"Contract terms comply with statutory requirements under {statute_info['citation']}."

        # Case 1: SECURITY DEPOSIT / COMMERCIAL SECURITY DEPOSIT
        if topic_norm in ("SECURITY_DEPOSIT", "COMMERCIAL_SECURITY_DEPOSIT"):
            is_comm = (
                request.property_type == "commercial"
                or topic_norm == "COMMERCIAL_SECURITY_DEPOSIT"
                or (winning_clause and "commercial" in (winning_clause.get("instrument") or winning_clause.get("agreement_title") or "").lower())
            )
            if is_comm and topic_norm != "SECURITY_DEPOSIT":
                statute_info["citation"] = "Cal. Civ. Code § 1950.7(f)"
                statute_info["mandate_type"] = "STATUTORY_PERMISSIVE_WAIVER"
                alignment = "aligned"
                enforceability = "ENFORCEABLE"
                explanation = (
                    "Commercial tenancy deposit governed by Cal. Civ. Code § 1950.7; freedom of contract applies "
                    "and statutory 1-month residential cap under AB 12 is inapplicable."
                )
            elif is_comm and request.property_type == "commercial":
                statute_info["citation"] = "Cal. Civ. Code § 1950.7"
                statute_info["mandate_type"] = "STATUTORY_PERMISSIVE_WAIVER"
                alignment = "aligned"
                enforceability = "ENFORCEABLE"
                explanation = (
                    "Commercial tenancy security deposit governed by Cal. Civ. Code § 1950.7; "
                    "AB 12 1-month ceiling does not apply to commercial real property leases."
                )
            else:
                stat_cap = statute_info["normalized_slot"].get("deposit_cap_months", 1.0)
                contract_val = (
                    contract_slots.get("deposit_cap_months")
                    or contract_slots.get("deposit_months")
                    or contract_slots.get("max_months")
                    or contract_slots.get("security_deposit_months")
                )
                # Regex fallback extraction from clause content if not in structured slots
                if contract_val is None and winning_clause.get("content"):
                    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:months?'?\s*(?:rent|deposit))", winning_clause["content"], re.IGNORECASE)
                    if m:
                        contract_val = float(m.group(1))

                if contract_val is not None:
                    contract_val = float(contract_val)
                    if contract_val > stat_cap:
                        alignment = "contract_less_than_mandatory"
                        enforceability = "VOID_AS_AGAINST_PUBLIC_POLICY"
                        explanation = (
                            f"Contract demands {contract_val} months rent security deposit, violating non-waivable statutory ceiling of "
                            f"{stat_cap} month(s) under {statute_info['citation']} as of {as_of}."
                        )
                        has_non_compliant = True
                    else:
                        alignment = "aligned"
                        enforceability = "ENFORCEABLE"
                        explanation = f"Contract deposit of {contract_val} months conforms to statutory ceiling ({stat_cap} months)."

        # Case 2: ENTRY NOTICE
        elif topic_norm == "ENTRY_NOTICE":
            stat_min = statute_info["normalized_slot"].get("entry_notice_hours", 24.0)
            contract_val = (
                contract_slots.get("entry_notice_hours")
                or contract_slots.get("notice_hours")
                or contract_slots.get("min_hours")
            )
            if contract_val is None and winning_clause.get("content"):
                m = re.search(r"(\d+)\s*(?:hours?'?\s*notice)", winning_clause["content"], re.IGNORECASE)
                if m:
                    contract_val = float(m.group(1))

            if contract_val is not None:
                contract_val = float(contract_val)
                if contract_val < stat_min:
                    alignment = "contract_less_than_mandatory"
                    enforceability = "VOID_AS_AGAINST_PUBLIC_POLICY"
                    explanation = (
                        f"Contract provides {contract_val} hours entry notice, violating statutory minimum floor of "
                        f"{stat_min} hours under {statute_info['citation']}."
                    )
                    has_non_compliant = True
                elif contract_val > stat_min:
                    alignment = "contract_more_generous"
                    enforceability = "ENFORCEABLE"
                    explanation = f"Contract grants {contract_val} hours advance notice, exceeding statutory floor of {stat_min} hours."
                else:
                    alignment = "aligned"
                    enforceability = "ENFORCEABLE"
                    explanation = f"Contract entry notice ({contract_val} hrs) matches statutory minimum requirement."

        # Case 3: DEPOSIT RETURN TIMELINE
        elif topic_norm == "DEPOSIT_RETURN":
            stat_max_days = statute_info["normalized_slot"].get("deposit_return_days", 21.0)
            contract_days = (
                contract_slots.get("deposit_return_days")
                or contract_slots.get("return_days")
                or contract_slots.get("accounting_days")
            )
            if contract_days is None and winning_clause.get("content"):
                m = re.search(r"(\d+)\s*(?:calendar\s+|business\s+)?days?", winning_clause["content"], re.IGNORECASE)
                if m:
                    contract_days = float(m.group(1))

            if contract_days is not None:
                contract_days = float(contract_days)
                if contract_days > stat_max_days:
                    alignment = "contract_less_than_mandatory"
                    enforceability = "VOID_AS_AGAINST_PUBLIC_POLICY"
                    explanation = (
                        f"Contract provides {contract_days:.0f} days to return deposit/accounting, violating non-waivable "
                        f"{stat_max_days:.0f}-day statutory ceiling under {statute_info['citation']}."
                    )
                    has_non_compliant = True
                elif contract_days < stat_max_days:
                    alignment = "contract_more_generous"
                    enforceability = "ENFORCEABLE"
                    explanation = f"Contract grants {contract_days:.0f} days to return deposit, more generous than statutory ceiling of {stat_max_days:.0f} days."
                else:
                    alignment = "aligned"
                    enforceability = "ENFORCEABLE"
                    explanation = f"Contract deposit return timeline ({contract_days:.0f} days) complies with 21-day statutory deadline."

        # Case 4: HABITABILITY WAIVER / REPAIR AND DEDUCT
        elif topic_norm in ("HABITABILITY_WAIVER", "REPAIR_AND_DEDUCT"):
            waives_hab = (
                contract_slots.get("waives_habitability") is True
                or contract_slots.get("waives_repair_deduct") is True
                or contract_slots.get("as_is") is True
            )
            if not waives_hab and winning_clause.get("content"):
                content_raw = winning_clause["content"].lower()
                if re.search(r"waives?\s+(?:all\s+)?(?:rights?\s+under\s+(?:sections?\s+)?194[12]|implied\s+warranty|repair\s+and\s+deduct)", content_raw):
                    waives_hab = True
                elif "as-is" in content_raw and ("habitability" in content_raw or "repair" in content_raw or "disclaim" in content_raw):
                    waives_hab = True

            if waives_hab:
                alignment = "contract_less_than_mandatory"
                enforceability = "VOID_AS_AGAINST_PUBLIC_POLICY"
                explanation = (
                    f"Contract purports to waive statutory habitability protections or repair-and-deduct rights, "
                    f"which is declared VOID AS AGAINST PUBLIC POLICY under {statute_info['citation']}."
                )
                has_non_compliant = True
            else:
                alignment = "aligned"
                enforceability = "ENFORCEABLE"
                explanation = f"Contract terms comply with non-waivable statutory habitability standards under {statute_info['citation']}."

        # Case 5: RETALIATION WAIVER
        elif topic_norm == "RETALIATION_WAIVER":
            waives_ret = contract_slots.get("waives_retaliation_defense") is True
            if not waives_ret and winning_clause.get("content"):
                content_raw = winning_clause["content"].lower()
                if re.search(r"waives?\s+(?:all\s+)?(?:rights?\s+under\s+(?:section\s+)?1942\.5|retaliat)", content_raw):
                    waives_ret = True

            if waives_ret:
                alignment = "contract_less_than_mandatory"
                enforceability = "VOID_AS_AGAINST_PUBLIC_POLICY"
                explanation = (
                    f"Contract purports to waive statutory retaliation defenses, which is declared "
                    f"VOID AS AGAINST PUBLIC POLICY under {statute_info['citation']}."
                )
                has_non_compliant = True
            else:
                alignment = "aligned"
                enforceability = "ENFORCEABLE"
                explanation = f"Contract preserves statutory retaliation protections under {statute_info['citation']}."

        # Case 6: LATE FEE / USURY
        elif topic_norm in ("LATE_FEE", "PAYMENT_TERMS"):
            stat_max = statute_info["normalized_slot"].get("max_pct", 10.0)
            contract_pct = (
                contract_slots.get("late_penalty_pct")
                or contract_slots.get("late_interest_pct")
                or contract_slots.get("interest_pct")
            )
            if contract_pct is not None:
                contract_pct = float(contract_pct)
                if contract_pct > stat_max:
                    alignment = "contract_less_than_mandatory"
                    enforceability = "VOID_AS_AGAINST_PUBLIC_POLICY"
                    explanation = (
                        f"Contract fee/interest of {contract_pct}% exceeds non-waivable statutory ceiling of "
                        f"{stat_max}% under {statute_info['citation']}."
                    )
                    has_non_compliant = True

        findings.append(ComplianceFinding(
            topic=topic_norm,
            alignment=alignment,
            enforceability=enforceability,
            contract_clause=contract_clause_info,
            controlling_statute=statute_info,
            explanation=explanation,
            trace_id=trace_id
        ))

    # Overall verdict
    if has_non_compliant:
        verdict = "NON_COMPLIANT_TERMS_FOUND"
    elif has_coverage_gap:
        verdict = "COVERAGE_GAPS_IDENTIFIED"
    else:
        verdict = "COMPLIANT"

    return ContractVsStatuteResponse(
        verdict=verdict,
        as_of_date=str(as_of),
        jurisdiction=request.jurisdiction,
        counterparty=counterparty,
        findings=findings
    )
