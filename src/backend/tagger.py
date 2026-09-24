"""
src/backend/tagger.py
=====================
KruschBiz Commercial Semantic Chunk Tagger.
Extracts structured commercial taxonomy tags, 1-sentence micro-digests,
and canonical topic classifications for contract chunks and deal exhibits.

Mirrors krusch-law and krusch-git semantic tagging agents, bridging the gap between
unstructured deal exhibits/redlines and structured corporate taxonomy and governance rules.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .config import settings
from .taxonomy import (
    CANONICAL_TOPICS,
    classify_topic,
    extract_structured_slots,
)

logger = logging.getLogger("kruschbiz.tagger")

TAGGER_SYSTEM_PROMPT = """You are an expert corporate legal and commercial knowledge architect.
Given an enterprise contract chunk or deal exhibit with its citation locator, output a JSON object with:
- "summary": A precise 1-sentence commercial or factual micro-digest (max 140 chars) of what this chunk establishes or obligates.
- "tags": An array of 3-5 lowercase semantic tags (e.g. ["payment-terms", "net-30", "late-fee", "interest-penalty"] or ["liability-cap", "consequential-damages", "carve-out"]).
- "topic": The canonical commercial topic: "PAYMENT_TERMS", "LIMITATION_OF_LIABILITY", "INDEMNIFICATION", "SLA_PERFORMANCE", "DATA_PROTECTION", "TERMINATION", "AUDIT_RIGHTS", "CONFIDENTIALITY", "WARRANTIES", "GOVERNING_LAW", or "GENERAL_COMMERCIAL".

Rules:
- Never use filler phrases like "This excerpt discusses..." or "The document says..."
- Output ONLY valid raw JSON. No markdown fences, no backticks, no explanatory text.
"""

TOPIC_TAG_DEFAULTS: dict[str, list[str]] = {
    "PAYMENT_TERMS": ["payment-terms", "invoicing", "due-date"],
    "LIMITATION_OF_LIABILITY": ["limitation-of-liability", "liability-cap", "damages-exclusion"],
    "INDEMNIFICATION": ["indemnification", "hold-harmless", "third-party-defense"],
    "SLA_PERFORMANCE": ["service-level-agreement", "uptime-commitment", "availability"],
    "DATA_PROTECTION": ["data-protection", "security-incident", "confidentiality"],
    "TERMINATION": ["termination", "cure-period", "material-breach"],
    "AUDIT_RIGHTS": ["audit-rights", "books-and-records", "inspection"],
    "CONFIDENTIALITY": ["confidentiality", "non-disclosure", "proprietary-information"],
    "WARRANTIES": ["warranties", "disclaimer", "remedy"],
    "GOVERNING_LAW": ["governing-law", "jurisdiction", "dispute-resolution"],
    "GENERAL_COMMERCIAL": ["commercial-terms", "contract-clause", "deal-record"]
}


def sanitize_tag(raw: str) -> str:
    """Sanitize tag to lowercase alphanumeric characters and hyphens."""
    cleaned = re.sub(r'[^a-z0-9\-]', '', str(raw).lower().strip().replace(" ", "-").replace("_", "-"))
    return re.sub(r'-+', '-', cleaned).strip("-")


def heuristic_tag_commercial_chunk(
    content: str,
    filename: str = "",
    locator: str | None = None,
    doc_type: str | None = None
) -> dict[str, Any]:
    """
    Deterministic rule-based commercial tagger for zero-latency tagging.
    Serves as an offline fallback when Ollama is unavailable or in resource-constrained environments.
    """
    clean_text = content.strip()
    first_period = clean_text.find(".")
    if 0 < first_period < 140:
        summary = clean_text[:first_period + 1].strip()
    else:
        summary = (clean_text[:137] + "...").strip() if len(clean_text) > 140 else clean_text

    combined_text = f"{filename} {locator or ''} {content}"
    topic = classify_topic(combined_text)
    _, slots = extract_structured_slots(content, topic=topic)

    matched_tags: list[str] = list(TOPIC_TAG_DEFAULTS.get(topic, TOPIC_TAG_DEFAULTS["GENERAL_COMMERCIAL"]))

    # Slot-derived high-precision semantic tags
    if "net_days" in slots:
        matched_tags.insert(0, f"net-{slots['net_days']}")
    if "late_interest_pct" in slots:
        matched_tags.append(f"late-interest-{slots['late_interest_pct']}pct")
    if "uptime_pct" in slots:
        matched_tags.insert(0, f"uptime-{slots['uptime_pct']}pct")
    if "credit_pct" in slots:
        matched_tags.append(f"credit-{slots['credit_pct']}pct")
    if "notice_hours" in slots:
        matched_tags.append(f"notice-{slots['notice_hours']}h")
    if "notice_days" in slots:
        matched_tags.append(f"notice-{slots['notice_days']}d")
    if "cure_days" in slots:
        matched_tags.append(f"cure-{slots['cure_days']}d")
    if "cap_period_months" in slots:
        matched_tags.append(f"cap-{slots['cap_period_months']}mo")
    if "cap_amount" in slots:
        matched_tags.append("monetary-cap")
    if "exclusive_remedy" in slots:
        matched_tags.append("exclusive-remedy")
    if "carve_outs" in slots:
        for co in slots["carve_outs"]:
            matched_tags.append(sanitize_tag(co))

    # Doc type tag
    if doc_type and doc_type not in ("general", "contract", "commercial"):
        matched_tags.append(sanitize_tag(doc_type))

    # Section / Locator tag
    sec_match = re.findall(r'(?:section|clause|exhibit|art(?:icle)?|§)\s*([\w\.\-]+)', combined_text, re.IGNORECASE)
    for s in sec_match[:2]:
        cleaned_sec = sanitize_tag(s)
        if cleaned_sec:
            matched_tags.append(f"sec-{cleaned_sec}")

    # Deduplicate while preserving order, max 5 tags
    seen = set()
    deduped_tags: list[str] = []
    for t in matched_tags:
        ct = sanitize_tag(t)
        if ct and ct not in seen:
            seen.add(ct)
            deduped_tags.append(ct)
            if len(deduped_tags) >= 5:
                break

    if not deduped_tags:
        deduped_tags = ["deal-record", "commercial-terms"]

    return {
        "summary": summary,
        "tags": deduped_tags,
        "topic": topic
    }


def tag_commercial_chunk_with_llm(
    content: str,
    filename: str = "",
    locator: str | None = None,
    doc_type: str | None = None,
    timeout: float | None = None
) -> dict[str, Any] | None:
    """
    Request structured commercial tags, micro-digest summary, and topic from local Ollama.
    """
    to = timeout or float(getattr(settings, "TAGGER_TIMEOUT", 15.0))
    model = getattr(settings, "TAGGER_MODEL", getattr(settings, "OLLAMA_LLM_MODEL", "qwen2.5-coder:7b"))
    host = settings.OLLAMA_BASE_URL.rstrip("/")

    truncated_content = content[:3000]
    loc_info = f" (Locator: {locator})" if locator else ""
    user_prompt = (
        f"Document: {filename}{loc_info}\n"
        f"Classification: {doc_type or 'unspecified'}\n\n"
        f"Commercial Chunk Text:\n```\n{truncated_content}\n```"
    )

    try:
        with httpx.Client(timeout=to) as client:
            resp = client.post(
                f"{host}/api/generate",
                json={
                    "model": model,
                    "system": TAGGER_SYSTEM_PROMPT,
                    "prompt": user_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 150,
                        "top_p": 0.9
                    }
                }
            )
            if resp.status_code != 200:
                logger.warning(f"Ollama tagger status {resp.status_code}: {resp.text[:100]}")
                return None

            data = resp.json()
            raw = (data.get("response") or "").strip()
            if not raw:
                return None

            # Clean JSON formatting
            cleaned = raw
            cleaned = re.sub(r'^```json?\s*', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            last_brace = cleaned.rfind('}')
            if last_brace > 0:
                cleaned = cleaned[:last_brace + 1]

            parsed = json.loads(cleaned)
            summary = str(parsed.get("summary") or "").strip()[:140]
            raw_tags = parsed.get("tags") or []
            raw_topic = str(parsed.get("topic") or "").strip().upper()

            if not summary or not isinstance(raw_tags, list):
                return None

            topic = raw_topic if raw_topic in CANONICAL_TOPICS else classify_topic(content)

            clean_tags: list[str] = []
            seen = set()
            for t in raw_tags[:5]:
                ct = sanitize_tag(str(t))
                if ct and ct not in seen:
                    seen.add(ct)
                    clean_tags.append(ct)

            if not clean_tags:
                return None

            return {
                "summary": summary,
                "tags": clean_tags,
                "topic": topic
            }
    except Exception as e:
        logger.debug(f"LLM tagging unavailable or failed ({e}); falling back to heuristic tagger.")
        return None


def tag_commercial_chunk(
    content: str,
    filename: str = "",
    locator: str | None = None,
    doc_type: str | None = None,
    use_llm: bool = True
) -> dict[str, Any]:
    """
    Primary interface for commercial chunk tagging.
    Combines deterministic slot extraction and keyword heuristics with
    LLM semantic understanding for true ensemble tagging.
    """
    heuristic = heuristic_tag_commercial_chunk(
        content=content,
        filename=filename,
        locator=locator,
        doc_type=doc_type
    )

    if use_llm:
        res = tag_commercial_chunk_with_llm(
            content=content,
            filename=filename,
            locator=locator,
            doc_type=doc_type
        )
        if res is not None and res.get("tags"):
            # Ensemble merge: combine deterministic slot tags + LLM tags
            seen = set()
            merged_tags: list[str] = []

            # 1. Prioritize slot-derived tags (net-..., uptime-..., cap-..., sec-...)
            for t in heuristic.get("tags", []):
                ct = sanitize_tag(t)
                if ct and ct not in seen:
                    seen.add(ct)
                    merged_tags.append(ct)

            # 2. Add LLM semantic tags
            for t in res.get("tags", []):
                ct = sanitize_tag(t)
                if ct and ct not in seen:
                    seen.add(ct)
                    merged_tags.append(ct)
                    if len(merged_tags) >= 7:
                        break

            assigned_topic = res.get("topic")
            if not assigned_topic or assigned_topic == "GENERAL_COMMERCIAL":
                assigned_topic = heuristic.get("topic", "GENERAL_COMMERCIAL")

            summary_text = res.get("summary") or heuristic.get("summary")

            return {
                "summary": summary_text,
                "tags": merged_tags[:7],
                "topic": assigned_topic
            }

    return heuristic

