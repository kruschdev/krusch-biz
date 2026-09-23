"""
src/backend/taxonomy.py
=======================
Closed commercial contract and corporate policy taxonomy with open structured slot extraction.
Extracts numeric, temporal, and categorical terms into verifiable structured slots.
"""

from __future__ import annotations

import re
from typing import Any

# Canonical taxonomy topics
TOPIC_PAYMENT_TERMS = "PAYMENT_TERMS"
TOPIC_LIMITATION_OF_LIABILITY = "LIMITATION_OF_LIABILITY"
TOPIC_INDEMNIFICATION = "INDEMNIFICATION"
TOPIC_SLA_PERFORMANCE = "SLA_PERFORMANCE"
TOPIC_DATA_PROTECTION = "DATA_PROTECTION"
TOPIC_TERMINATION = "TERMINATION"
TOPIC_AUDIT_RIGHTS = "AUDIT_RIGHTS"
TOPIC_CONFIDENTIALITY = "CONFIDENTIALITY"
TOPIC_WARRANTIES = "WARRANTIES"
TOPIC_GOVERNING_LAW = "GOVERNING_LAW"

CANONICAL_TOPICS = [
    TOPIC_PAYMENT_TERMS,
    TOPIC_LIMITATION_OF_LIABILITY,
    TOPIC_INDEMNIFICATION,
    TOPIC_SLA_PERFORMANCE,
    TOPIC_DATA_PROTECTION,
    TOPIC_TERMINATION,
    TOPIC_AUDIT_RIGHTS,
    TOPIC_CONFIDENTIALITY,
    TOPIC_WARRANTIES,
    TOPIC_GOVERNING_LAW,
]

# Topic classification keywords
TOPIC_KEYWORDS: dict[str, list[str]] = {
    TOPIC_PAYMENT_TERMS: ["net 30", "net 45", "net 60", "invoice", "payment", "late fee", "late interest", "due date"],
    TOPIC_LIMITATION_OF_LIABILITY: ["limitation of liability", "liability cap", "consequential damages", "aggregate liability", "in no event shall", "cap on liability"],
    TOPIC_INDEMNIFICATION: ["indemnify", "indemnification", "hold harmless", "defend", "infringement claim", "third-party claim"],
    TOPIC_SLA_PERFORMANCE: ["uptime", "service level", "sla", "availability", "service credit", "scheduled maintenance", "downtime"],
    TOPIC_DATA_PROTECTION: ["data protection", "security incident", "breach notice", "personal data", "gdpr", "dpa", "security breach"],
    TOPIC_TERMINATION: ["termination for convenience", "termination for cause", "cure period", "material breach", "immediate termination"],
    TOPIC_AUDIT_RIGHTS: ["audit", "inspection", "books and records", "examination", "access to records"],
    TOPIC_CONFIDENTIALITY: ["confidential information", "non-disclosure", "proprietary information", "trade secret"],
    TOPIC_WARRANTIES: ["warranty", "warranties", "disclaimer", "as is", "merchantability", "sole and exclusive remedy"],
    TOPIC_GOVERNING_LAW: ["governing law", "jurisdiction", "venue", "laws of the state of", "arbitration"],
}


def classify_topic(text: str) -> str:
    """Classify text into a canonical commercial taxonomy topic."""
    text_lower = text.lower()
    scores: dict[str, int] = {topic: 0 for topic in CANONICAL_TOPICS}

    for topic, kw_list in TOPIC_KEYWORDS.items():
        for kw in kw_list:
            if kw in text_lower:
                scores[topic] += 1

    best_topic = max(scores, key=lambda k: scores[k])
    return best_topic if scores[best_topic] > 0 else "GENERAL_COMMERCIAL"


def extract_structured_slots(text: str, topic: str | None = None) -> tuple[str, dict[str, Any]]:
    """
    Extract structured commercial slots (numbers, percentages, timeframes, carve-outs)
    from clause text into a validated dictionary.
    """
    if not topic or topic == "GENERAL_COMMERCIAL":
        topic = classify_topic(text)

    slots: dict[str, Any] = {}
    text_lower = text.lower()

    # 1. Payment Terms Slots
    net_match = re.search(r"\bnet\s+(\d{1,3})\b", text_lower)
    if net_match:
        slots["net_days"] = int(net_match.group(1))
    else:
        within_days_match = re.search(r"within\s+(\w+)\s*\((\d{1,3})\)\s*days\s+of\s+(?:the\s+)?invoice", text_lower)
        if within_days_match:
            slots["net_days"] = int(within_days_match.group(2))

    interest_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:per\s+month|monthly|late\s+interest)", text_lower)
    if interest_match:
        slots["late_interest_pct"] = float(interest_match.group(1))

    # 2. SLA / Performance Slots
    uptime_match = re.search(r"(\d{2}(?:\.\d{1,3})?)\s*%\s*(?:uptime|availability)", text_lower)
    if uptime_match:
        slots["uptime_pct"] = float(uptime_match.group(1))

    credit_match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%\s*(?:credit|service\s+credit)", text_lower)
    if credit_match:
        slots["credit_pct"] = float(credit_match.group(1))

    # 3. Data Protection / Breach Notice Slots
    notice_hours_match = re.search(r"within\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*hours", text_lower)
    if notice_hours_match:
        hours = notice_hours_match.group(1) or notice_hours_match.group(2)
        slots["notice_hours"] = int(hours)

    # 4. Notice Days (Termination, Audit, Cure, Acceptance)
    notice_days_match = re.search(r"(?:within|upon|at\s+least)?\s*(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*(?:business\s+)?days", text_lower)
    if notice_days_match and "net_days" not in slots:
        days = notice_days_match.group(1) or notice_days_match.group(2)
        slots["notice_days"] = int(days)

    cure_match = re.search(r"cure\s+period\s+of\s+(?:\w+\s*\((\d{1,3})\)|(\d{1,3}))\s*days", text_lower)
    if cure_match:
        days = cure_match.group(1) or cure_match.group(2)
        slots["cure_days"] = int(days)

    # 5. Limitation of Liability & Monetary Amount Slots
    cap_months_match = re.search(r"(\d{1,2})\s*months\s+(?:of\s+)?(?:fees|paid|preceding)", text_lower)
    if cap_months_match:
        slots["cap_period_months"] = int(cap_months_match.group(1))

    cap_amount_match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text)
    if cap_amount_match:
        clean_amount = cap_amount_match.group(1).replace(",", "")
        try:
            slots["cap_amount"] = float(clean_amount)
        except ValueError:
            pass

    # Carve-outs
    carve_outs: list[str] = []
    if "gross negligence" in text_lower:
        carve_outs.append("gross_negligence")
    if "willful misconduct" in text_lower or "wilful misconduct" in text_lower:
        carve_outs.append("willful_misconduct")
    if "confidentiality" in text_lower and ("breach" in text_lower or "obligations" in text_lower):
        carve_outs.append("confidentiality_breach")
    if "indemnification" in text_lower or "indemnity" in text_lower:
        carve_outs.append("indemnification")
    if carve_outs:
        slots["carve_outs"] = carve_outs

    # Exclusive remedy
    if "sole and exclusive remedy" in text_lower or "exclusive remedy" in text_lower:
        slots["exclusive_remedy"] = True

    return topic, slots
