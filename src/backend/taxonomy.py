"""
src/backend/taxonomy.py
=======================
Closed commercial contract and corporate policy taxonomy with typed structured slot extraction
and exact span provenance.
Extracts numeric, temporal, and categorical terms into verifiable structured slots conforming to:
  {value, unit, raw_span, char_start, char_end, pattern_id, confidence}

Features:
  - Unified 13+ canonical commercial topics (aligned with README and legal precedence)
  - Trigger discrimination: separates liability caps from monthly/hourly retainers and fees
  - Trigger discrimination: separates breach cure periods from invoice dispute, suspension,
    and termination notice intervals
  - Bidirectional helper functions (get_slot_val, slot_dict_to_primitives) for seamless
    interoperability with legacy primitive slots and typed span provenance.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


class TypedSlot(TypedDict):
    value: Any                  # Primitive value (int, float, str, bool, list)
    unit: str                   # e.g. "days", "%", "%/month", "USD", "months", "hours", "boolean", "carve_outs"
    raw_span: str               # Exact substring from the clause text
    char_start: int             # Exact start index in clause text
    char_end: int               # Exact end index in clause text
    pattern_id: str             # Identifier for the regex / extraction pattern
    confidence: float           # Rubric confidence score (0.0 - 1.0)


# ---------------------------------------------------------------------------
# CANONICAL COMMERCIAL TAXONOMY TOPICS
# ---------------------------------------------------------------------------

TOPIC_PAYMENT_TERMS = "PAYMENT_TERMS"
TOPIC_LATE_FEE = "LATE_FEE"
TOPIC_LIABILITY_CAP = "LIABILITY_CAP"
TOPIC_LIMITATION_OF_LIABILITY = "LIMITATION_OF_LIABILITY"  # Standard alias for LIABILITY_CAP
TOPIC_LIABILITY_CARVE_OUT = "LIABILITY_CARVE_OUT"
TOPIC_INDEMNITY = "INDEMNITY"
TOPIC_INDEMNIFICATION = "INDEMNIFICATION"                  # Standard alias for INDEMNITY
TOPIC_SLA_UPTIME = "SLA_UPTIME"
TOPIC_SLA_CREDIT = "SLA_CREDIT"
TOPIC_SLA_PERFORMANCE = "SLA_PERFORMANCE"                # Standard alias for SLA_UPTIME
TOPIC_DATA_PROTECTION = "DATA_PROTECTION"
TOPIC_BREACH_NOTIFICATION = "BREACH_NOTIFICATION"
TOPIC_AUDIT_RIGHTS = "AUDIT_RIGHTS"
TOPIC_TERMINATION_CONVENIENCE = "TERMINATION_CONVENIENCE"
TOPIC_TERMINATION = "TERMINATION"                          # Standard alias for TERMINATION_CONVENIENCE
TOPIC_MOST_FAVORED_NATION = "MOST_FAVORED_NATION"
TOPIC_GOVERNING_LAW = "GOVERNING_LAW"
TOPIC_CONFIDENTIALITY = "CONFIDENTIALITY"
TOPIC_WARRANTIES = "WARRANTIES"

CANONICAL_TOPICS: list[str] = [
    TOPIC_PAYMENT_TERMS,
    TOPIC_LATE_FEE,
    TOPIC_LIABILITY_CAP,
    TOPIC_LIMITATION_OF_LIABILITY,
    TOPIC_LIABILITY_CARVE_OUT,
    TOPIC_INDEMNITY,
    TOPIC_INDEMNIFICATION,
    TOPIC_SLA_UPTIME,
    TOPIC_SLA_CREDIT,
    TOPIC_SLA_PERFORMANCE,
    TOPIC_DATA_PROTECTION,
    TOPIC_BREACH_NOTIFICATION,
    TOPIC_AUDIT_RIGHTS,
    TOPIC_TERMINATION_CONVENIENCE,
    TOPIC_TERMINATION,
    TOPIC_MOST_FAVORED_NATION,
    TOPIC_GOVERNING_LAW,
    TOPIC_CONFIDENTIALITY,
    TOPIC_WARRANTIES,
]

# Canonical alias normalization mapping
CANONICAL_TOPIC_ALIASES: dict[str, str] = {
    "LIABILITY_CAP": TOPIC_LIMITATION_OF_LIABILITY,
    "INDEMNITY": TOPIC_INDEMNIFICATION,
    "SLA_UPTIME": TOPIC_SLA_PERFORMANCE,
    "SLA_CREDIT": TOPIC_SLA_PERFORMANCE,
    "BREACH_NOTIFICATION": TOPIC_DATA_PROTECTION,
    "TERMINATION_CONVENIENCE": TOPIC_TERMINATION,
}

# Topic classification keywords
TOPIC_KEYWORDS: dict[str, list[str]] = {
    TOPIC_PAYMENT_TERMS: ["net 30", "net 45", "net 60", "net 90", "invoice", "payment terms", "due date", "invoicing schedule"],
    TOPIC_LATE_FEE: ["late fee", "late interest", "interest rate", "delinquent amounts", "accrue late interest"],
    TOPIC_LIMITATION_OF_LIABILITY: ["limitation of liability", "liability cap", "consequential damages", "aggregate liability", "in no event shall", "cap on liability"],
    TOPIC_LIABILITY_CARVE_OUT: ["carve-out", "carveout", "gross negligence", "willful misconduct", "unlimited liability", "except for liability arising"],
    TOPIC_INDEMNIFICATION: ["indemnify", "indemnification", "hold harmless", "defend", "infringement claim", "third-party claim"],
    TOPIC_SLA_PERFORMANCE: ["uptime", "service level", "sla", "availability", "service credit", "scheduled maintenance", "downtime"],
    TOPIC_DATA_PROTECTION: ["data protection", "security incident", "breach notice", "personal data", "gdpr", "dpa", "security breach", "soc2"],
    TOPIC_AUDIT_RIGHTS: ["audit", "inspection", "books and records", "examination", "access to records", "audit rights"],
    TOPIC_TERMINATION: ["termination for convenience", "termination for cause", "cure period", "material breach", "immediate termination"],
    TOPIC_MOST_FAVORED_NATION: ["most favored nation", "mfn", "equal or better terms", "lowest pricing"],
    TOPIC_GOVERNING_LAW: ["governing law", "jurisdiction", "venue", "laws of the state of", "arbitration"],
    TOPIC_CONFIDENTIALITY: ["confidential information", "non-disclosure", "proprietary information", "trade secret"],
    TOPIC_WARRANTIES: ["warranty", "warranties", "disclaimer", "as is", "merchantability", "sole and exclusive remedy"],
}


def normalize_topic(topic: str | None) -> str:
    """Normalize topic alias to primary canonical topic name."""
    if not topic:
        return "GENERAL_COMMERCIAL"
    norm = topic.strip().upper()
    return CANONICAL_TOPIC_ALIASES.get(norm, norm)


def classify_topic(text: str) -> str:
    """Classify text into a canonical commercial taxonomy topic."""
    text_lower = text.lower()
    scores: dict[str, int] = {topic: 0 for topic in TOPIC_KEYWORDS}

    for topic, kw_list in TOPIC_KEYWORDS.items():
        for kw in kw_list:
            if kw in text_lower:
                scores[topic] += 1

    best_topic = max(scores, key=lambda k: scores[k])
    return best_topic if scores[best_topic] > 0 else "GENERAL_COMMERCIAL"


# ---------------------------------------------------------------------------
# TYPED SLOT BUILDERS & HELPERS
# ---------------------------------------------------------------------------

def make_typed_slot(
    value: Any,
    unit: str,
    raw_span: str,
    char_start: int,
    char_end: int,
    pattern_id: str,
    confidence: float = 0.95
) -> TypedSlot:
    """Construct a typed structured slot with exact character span provenance."""
    return {
        "value": value,
        "unit": unit,
        "raw_span": raw_span,
        "char_start": char_start,
        "char_end": char_end,
        "pattern_id": pattern_id,
        "confidence": round(confidence, 4)
    }


def get_slot_val(slot: Any) -> Any:
    """
    Extract the primitive value from a TypedSlot dict or return the primitive directly.
    Guarantees backwards-compatibility across legacy tests and new typed slots.
    """
    if isinstance(slot, dict) and "value" in slot:
        return slot["value"]
    return slot


def slot_dict_to_primitives(slots: dict[str, Any]) -> dict[str, Any]:
    """Convert a dictionary of typed slots to flat primitive values."""
    return {k: get_slot_val(v) for k, v in slots.items()}


TAXONOMY_VERSION = 2


def classify_topic_from_slots(slots: dict[str, Any]) -> str | None:
    """Classify topic from authoritative structured slot signatures."""
    if "cap_amount" in slots or "carve_outs" in slots:
        return TOPIC_LIMITATION_OF_LIABILITY
    if "net_days" in slots or "late_interest_pct" in slots or "payment_dispute_notice_days" in slots:
        return TOPIC_PAYMENT_TERMS
    if "uptime_pct" in slots or "credit_pct" in slots:
        return TOPIC_SLA_PERFORMANCE
    if "notice_hours" in slots:
        return TOPIC_DATA_PROTECTION
    if "termination_notice_days" in slots or "cure_days" in slots:
        return TOPIC_TERMINATION
    if "exclusive_remedy" in slots:
        return TOPIC_WARRANTIES
    return None


def get_slot_spans(slots: dict[str, TypedSlot]) -> dict[str, dict[str, int | str]]:
    """Return dictionary mapping slot keys to {char_start, char_end, raw_span} for UI highlighting."""
    spans: dict[str, dict[str, int | str]] = {}
    for k, v in slots.items():
        if isinstance(v, dict) and "char_start" in v and "char_end" in v:
            spans[k] = {
                "char_start": v["char_start"],
                "char_end": v["char_end"],
                "raw_span": v.get("raw_span", "")
            }
    return spans


# ---------------------------------------------------------------------------
# STRUCTURED SLOT EXTRACTION WITH SPAN PROVENANCE & TRIGGER DISCRIMINATION
# ---------------------------------------------------------------------------

def extract_structured_slots(text: str, topic: str | None = None) -> tuple[str, dict[str, TypedSlot]]:
    """
    Extract structured commercial slots (numbers, percentages, timeframes, carve-outs)
    with exact span provenance: {value, unit, raw_span, char_start, char_end, pattern_id, confidence}.

    Applies trigger discrimination (Taxonomy Version 2):
      - Requires payment context for 'Net X' (rejects 'net 30 kg', 'Net 10 users').
      - Restricts monetary caps to limitation/cap context windows.
      - Requires SLA / commitment language for uptime percentages.
      - Requires cap/indemnity window + exception grammar for carve-outs.
      - Separates notice day namespaces without cross-slot locks.
      - Topic priority: Slot signature > Keyword count > Fallback.
    """
    slots: dict[str, TypedSlot] = {}
    text_lower = text.lower()

    # 1. Payment Terms Slots (Net Days)
    # Require payment/invoice context in surrounding text
    net_match = re.search(r"\bnet\s+(\d{1,3})\b", text_lower)
    if net_match:
        # Check if immediately followed by non-time unit (e.g. kg, users, seats, gb, mb, lbs, nodes)
        after_match = text_lower[net_match.end():net_match.end() + 20]
        is_physical_unit = bool(re.match(r"^\s*(?:kg|users?|seats?|nodes?|servers?|lbs?|units?|threads?|gb|mb|tb)\b", after_match))
        
        start_ctx = max(0, net_match.start() - 60)
        end_ctx = min(len(text_lower), net_match.end() + 60)
        surr = text_lower[start_ctx:end_ctx]
        is_payment_ctx = bool(re.search(
            r"\b(?:invoices?|payments?|days|remit|due|undisputed|terms|billing|charges|payable)\b",
            surr
        )) or bool(re.search(r"\bpay\b", surr))
        
        if is_payment_ctx and not is_physical_unit:
            span_str = text[net_match.start():net_match.end()]
            slots["net_days"] = make_typed_slot(
                value=int(net_match.group(1)),
                unit="days",
                raw_span=span_str,
                char_start=net_match.start(),
                char_end=net_match.end(),
                pattern_id="net_days_standard",
                confidence=0.99
            )
    
    if "net_days" not in slots:
        within_days_match = re.search(
            r"within\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*days\s+of\s+(?:the\s+)?invoice",
            text_lower
        )
        if within_days_match:
            days_str = within_days_match.group(1) or within_days_match.group(2)
            span_str = text[within_days_match.start():within_days_match.end()]
            slots["net_days"] = make_typed_slot(
                value=int(days_str),
                unit="days",
                raw_span=span_str,
                char_start=within_days_match.start(),
                char_end=within_days_match.end(),
                pattern_id="net_days_within_invoice",
                confidence=0.96
            )

    # 2. Late Interest / Penalties
    interest_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:per\s+month|monthly|late\s+interest)", text_lower)
    if interest_match:
        span_str = text[interest_match.start():interest_match.end()]
        slots["late_interest_pct"] = make_typed_slot(
            value=float(interest_match.group(1)),
            unit="%/month",
            raw_span=span_str,
            char_start=interest_match.start(),
            char_end=interest_match.end(),
            pattern_id="late_interest_pct_monthly",
            confidence=0.98
        )

    # 3. SLA / Performance Slots (Uptime & Service Credits)
    # Require SLA, availability, or commitment context
    uptime_match = re.search(r"(\d{2}(?:\.\d{1,3})?)\s*%\s*(?:uptime|availability)", text_lower)
    if uptime_match:
        start_ctx = max(0, uptime_match.start() - 80)
        end_ctx = min(len(text_lower), uptime_match.end() + 80)
        surr = text_lower[start_ctx:end_ctx]
        is_sla_ctx = any(w in surr for w in (
            "sla", "exhibit", "warrant", "commit", "monthly", "service level",
            "system", "guarantee", "target", "downtime", "maintenance", "performance", "cycle"
        ))
        if is_sla_ctx or (topic and topic in (TOPIC_SLA_UPTIME, TOPIC_SLA_PERFORMANCE)):
            span_str = text[uptime_match.start():uptime_match.end()]
            slots["uptime_pct"] = make_typed_slot(
                value=float(uptime_match.group(1)),
                unit="%",
                raw_span=span_str,
                char_start=uptime_match.start(),
                char_end=uptime_match.end(),
                pattern_id="uptime_pct_standard",
                confidence=0.98
            )

    credit_match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%\s*(?:credit|service\s+credit)", text_lower)
    if credit_match:
        span_str = text[credit_match.start():credit_match.end()]
        slots["credit_pct"] = make_typed_slot(
            value=float(credit_match.group(1)),
            unit="%",
            raw_span=span_str,
            char_start=credit_match.start(),
            char_end=credit_match.end(),
            pattern_id="service_credit_pct",
            confidence=0.95
        )

    # 4. Data Protection / Breach Notice Hours
    notice_hours_match = re.search(r"within\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*hours", text_lower)
    if notice_hours_match:
        hours = notice_hours_match.group(1) or notice_hours_match.group(2)
        span_str = text[notice_hours_match.start():notice_hours_match.end()]
        slots["notice_hours"] = make_typed_slot(
            value=int(hours),
            unit="hours",
            raw_span=span_str,
            char_start=notice_hours_match.start(),
            char_end=notice_hours_match.end(),
            pattern_id="breach_notice_hours",
            confidence=0.97
        )

    # 5. TRIGGER DISCRIMINATION: Notice Intervals & Timeframes (Decoupled Namespaces)
    # 5a. Breach Cure Period
    cure_match = re.search(r"(?:cure\s+(?:period\s+of\s+)?|within\s+)(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days\s+to\s+cure", text_lower)
    if not cure_match:
        cure_match = re.search(r"cure\s+period\s+of\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days", text_lower)
    if cure_match:
        days = cure_match.group(1) or cure_match.group(2)
        span_str = text[cure_match.start():cure_match.end()]
        slots["cure_days"] = make_typed_slot(
            value=int(days),
            unit="days",
            raw_span=span_str,
            char_start=cure_match.start(),
            char_end=cure_match.end(),
            pattern_id="breach_cure_days",
            confidence=0.96
        )

    # 5b. Payment Dispute Notice
    dispute_match = re.search(r"(?:dispute\s+[^\.\;]*within\s+|within\s+)(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days\s+of\s+(?:the\s+)?invoice\s+date", text_lower)
    if dispute_match:
        days = dispute_match.group(1) or dispute_match.group(2)
        span_str = text[dispute_match.start():dispute_match.end()]
        slots["payment_dispute_notice_days"] = make_typed_slot(
            value=int(days),
            unit="days",
            raw_span=span_str,
            char_start=dispute_match.start(),
            char_end=dispute_match.end(),
            pattern_id="payment_dispute_notice_days",
            confidence=0.94
        )

    # 5c. Delinquency / Service Suspension Notice
    suspend_match = re.search(r"suspend\s+[^\.\;]*upon\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days(?:\s+prior\s+written)?\s+notice", text_lower)
    if suspend_match:
        days = suspend_match.group(1) or suspend_match.group(2)
        span_str = text[suspend_match.start():suspend_match.end()]
        slots["delinquency_notice_days"] = make_typed_slot(
            value=int(days),
            unit="days",
            raw_span=span_str,
            char_start=suspend_match.start(),
            char_end=suspend_match.end(),
            pattern_id="delinquency_notice_days",
            confidence=0.94
        )

    # 5d. Termination for Convenience Notice
    term_notice_match = re.search(r"terminat[^\.\;]*upon\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days(?:\s+prior\s+written)?\s+notice", text_lower)
    if term_notice_match:
        days = term_notice_match.group(1) or term_notice_match.group(2)
        span_str = text[term_notice_match.start():term_notice_match.end()]
        slots["termination_notice_days"] = make_typed_slot(
            value=int(days),
            unit="days",
            raw_span=span_str,
            char_start=term_notice_match.start(),
            char_end=term_notice_match.end(),
            pattern_id="termination_notice_days",
            confidence=0.95
        )

    # 5e. General Notice Days (Independent namespace, never locked out by net_days)
    general_notice_match = re.search(r"(?:within|upon|at\s+least)\s*(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days(?:\s+prior\s+written)?\s+notice", text_lower)
    if general_notice_match:
        days = general_notice_match.group(1) or general_notice_match.group(2)
        span_str = text[general_notice_match.start():general_notice_match.end()]
        slots["notice_days"] = make_typed_slot(
            value=int(days),
            unit="days",
            raw_span=span_str,
            char_start=general_notice_match.start(),
            char_end=general_notice_match.end(),
            pattern_id="general_notice_days",
            confidence=0.90
        )
    elif "termination_notice_days" in slots:
        slots["notice_days"] = slots["termination_notice_days"]
    elif "delinquency_notice_days" in slots:
        slots["notice_days"] = slots["delinquency_notice_days"]

    # 6. TRIGGER DISCRIMINATION: Monetary Amounts (Liability Caps vs Retainers / Fees)
    cap_months_match = re.search(r"(\d{1,2})\s*months\s+(?:of\s+)?(?:fees|paid|preceding)", text_lower)
    if cap_months_match:
        span_str = text[cap_months_match.start():cap_months_match.end()]
        slots["cap_period_months"] = make_typed_slot(
            value=int(cap_months_match.group(1)),
            unit="months",
            raw_span=span_str,
            char_start=cap_months_match.start(),
            char_end=cap_months_match.end(),
            pattern_id="cap_period_months",
            confidence=0.95
        )

    # Monetary currency search: inspect context window strictly
    monetary_matches = list(re.finditer(r"\$\s*([\d,]+(?:\.\d{2})?)", text))
    for m in monetary_matches:
        clean_amount = m.group(1).replace(",", "")
        try:
            amt = float(clean_amount)
        except ValueError:
            continue

        start_ctx = max(0, m.start() - 60)
        end_ctx = min(len(text_lower), m.end() + 60)
        surrounding_text = text_lower[start_ctx:end_ctx]
        span_str = text[m.start():m.end()]

        is_cap_context = any(w in surrounding_text for w in [
            "liability", "aggregate", "maximum", "exceed", "capped", "in no event shall", "cap"
        ])
        is_fee_context = any(w in surrounding_text for w in [
            "retainer", "monthly fee", "service fee", "subscription", "hourly", "rate", "deposit"
        ])

        if is_cap_context and not is_fee_context:
            if "cap_amount" not in slots:
                slots["cap_amount"] = make_typed_slot(
                    value=amt,
                    unit="USD",
                    raw_span=span_str,
                    char_start=m.start(),
                    char_end=m.end(),
                    pattern_id="liability_cap_monetary",
                    confidence=0.98
                )
        elif is_fee_context and not is_cap_context:
            if "fee_amount" not in slots:
                slots["fee_amount"] = make_typed_slot(
                    value=amt,
                    unit="USD",
                    raw_span=span_str,
                    char_start=m.start(),
                    char_end=m.end(),
                    pattern_id="commercial_fee_amount",
                    confidence=0.95
                )
        else:
            # Topic-level tie-breaker: ONLY if topic is explicitly liability cap
            if topic in (TOPIC_LIABILITY_CAP, TOPIC_LIMITATION_OF_LIABILITY) and is_cap_context and "cap_amount" not in slots:
                slots["cap_amount"] = make_typed_slot(
                    value=amt,
                    unit="USD",
                    raw_span=span_str,
                    char_start=m.start(),
                    char_end=m.end(),
                    pattern_id="liability_cap_fallback",
                    confidence=0.90
                )

    # 7. Liability Carve-Outs
    # Require cap/indemnity window or exception grammar
    is_carveout_ctx = any(w in text_lower for w in (
        "except", "excluding", "exclusion", "carve-out", "carveout",
        "shall not apply", "not apply to", "notwithstanding", "other than",
        "limitation", "liability", "damages", "indemnif"
    ))
    carve_outs: list[str] = []
    if is_carveout_ctx:
        if "gross negligence" in text_lower:
            carve_outs.append("gross_negligence")
        if "willful misconduct" in text_lower or "wilful misconduct" in text_lower:
            carve_outs.append("willful_misconduct")
        if "confidentiality" in text_lower and ("breach" in text_lower or "obligations" in text_lower):
            carve_outs.append("confidentiality_breach")
        if "indemnification" in text_lower or "indemnity" in text_lower:
            carve_outs.append("indemnification")
        if carve_outs:
            slots["carve_outs"] = make_typed_slot(
                value=carve_outs,
                unit="carve_outs",
                raw_span=", ".join(carve_outs),
                char_start=0,
                char_end=len(text),
                pattern_id="liability_carve_outs",
                confidence=0.95
            )

    # 8. Exclusive Remedy
    if "sole and exclusive remedy" in text_lower or "exclusive remedy" in text_lower:
        rem_match = re.search(r"(?:sole\s+and\s+)?exclusive\s+remedy", text_lower)
        start_idx = rem_match.start() if rem_match else 0
        end_idx = rem_match.end() if rem_match else len(text)
        slots["exclusive_remedy"] = make_typed_slot(
            value=True,
            unit="boolean",
            raw_span=text[start_idx:end_idx],
            char_start=start_idx,
            char_end=end_idx,
            pattern_id="exclusive_remedy_clause",
            confidence=0.98
        )

    # Final Topic Priority: Slot signature > provided topic > classify_topic
    slot_topic = classify_topic_from_slots(slots)
    if slot_topic:
        final_topic = slot_topic
    elif topic and topic != "GENERAL_COMMERCIAL":
        final_topic = topic
    else:
        final_topic = classify_topic(text)

    return final_topic, slots
