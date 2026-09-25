"""
src/backend/relations.py
========================
Deterministic relation extraction and lifecycle management for the KruschBiz
relational contract graph.

Extracts candidate relation edges from raw contract text, preamble, recitals, and filename cues:
  - AMENDS: "this Amendment amends the Agreement dated...", "amends and supplements..."
  - SUPERSEDES: "supersedes in its entirety", "supersedes and replaces..."
  - INCORPORATES: "is incorporated by reference", "incorporated herein by reference..."
  - CARVES_OUT: "except as set forth in Exhibit...", "carves out...", "subject to Section..."
  - SCHEDULE_OF: "statement of work entered into pursuant to...", "governed by the MSA..."

Emits candidate edges with:
  {source_agreement_id, target_agreement_id, relation_type, clause_scope, extractor, confidence, span, status}

Enforces:
  - Live edges are never silent guesses (human accept/reject workflow via status='proposed'|'accepted')
  - Strict tenant isolation and deterministic target resolution
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from .db import Agreement, AgreementRelation

logger = logging.getLogger("kruschbiz.relations")


def normalize_title_tokens(text: str) -> list[str]:
    """Tokenize and clean title for fuzzy candidate matching."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower()).strip()
    stopwords = {
        "the", "that", "certain", "dated", "agreement", "of", "to", "for",
        "and", "by", "between", "an", "a", "in", "with", "as", "herein", "no"
    }
    return [t for t in cleaned.split() if len(t) > 1 and t not in stopwords]


def extract_candidate_relations(
    text: str,
    filename: str,
    tenant_id: str,
    db: Session,
    source_ag_id: int | None = None,
    auto_persist_proposed: bool = True
) -> list[dict[str, Any]]:
    """
    Extract candidate agreement relations directly from document text, recitals, and filename.
    Emits candidate edges with extractor, confidence, span, and status='proposed'.
    """
    candidates: list[dict[str, Any]] = []
    preamble_window = text[:4000]
    preamble_lower = preamble_window.lower()
    fn_lower = filename.lower()

    detected_cues: list[dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # 1. Deterministic Text Regex Patterns (Preamble / Recitals Window)
    # -------------------------------------------------------------------------

    # 1a. AMENDS: "this Amendment amends...", "amendment no. X to...", "amends and supplements..."
    amend_patterns = [
        (
            r"(?:this\s+)?amendment\s+(?:no\.?\s*(\d+|[a-z]+))?\s*(?:to|of)\s+(?:that\s+certain\s+)?([a-z0-9\s]+?)(?=\s+dated|\s+by\s+and\s+between|\s+entered|\.|\;|\,)",
            "preamble_amendment_to",
            0.95
        ),
        (
            r"amends\s+(?:and\s+supplements\s+)?(?:that\s+certain\s+)?([a-z0-9\s]+?)(?=\s+dated|\s+by\s+and\s+between|\s+entered|\.|\;|\,)",
            "preamble_amends_verb",
            0.92
        ),
        (
            r"entered\s+into\s+as\s+an\s+amendment\s+to\s+(?:the\s+)?([a-z0-9\s]+?)(?=\s+dated|\.|\;|\,)",
            "preamble_amendment_entered",
            0.92
        )
    ]
    for pattern, rule_name, conf in amend_patterns:
        m = re.search(pattern, preamble_lower)
        if m:
            target_str = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else m.group(1)
            target_str = (target_str or "Agreement").strip()
            span_start = max(0, m.start() - 10)
            span_end = min(len(preamble_window), m.end() + 30)
            detected_cues.append({
                "relation_type": "AMENDS",
                "target_hint": target_str,
                "span": preamble_window[span_start:span_end].strip(),
                "char_start": m.start(),
                "char_end": m.end(),
                "confidence": conf,
                "extractor": "regex",
                "rule": rule_name
            })
            break

    # 1b. SUPERSEDES: "supersedes in its entirety", "supersedes and replaces..."
    supersedes_patterns = [
        (
            r"supersedes\s+(?:and\s+replaces\s+)?(?:in\s+its\s+entirety\s+)?(?:that\s+certain\s+)?([a-z0-9\s]+?)(?=\s+dated|\s+by\s+and\s+between|\s+entered|\.|\;|\,)",
            "preamble_supersedes_entirety",
            0.96
        ),
        (
            r"shall\s+supersede\s+(?:and\s+replace\s+)?(?:all\s+prior\s+)?([a-z0-9\s]+?)(?=\s+dated|\.|\;|\,)",
            "preamble_shall_supersede",
            0.93
        ),
        (
            r"amended\s+and\s+restated\s+([a-z0-9\s]+?)(?=\s+dated|\s+by\s+and\s+between|\.|\;|\,)",
            "preamble_amended_and_restated",
            0.90
        )
    ]
    for pattern, rule_name, conf in supersedes_patterns:
        m = re.search(pattern, preamble_lower)
        if m:
            target_str = (m.group(1) or "Agreement").strip()
            span_start = max(0, m.start() - 10)
            span_end = min(len(preamble_window), m.end() + 30)
            detected_cues.append({
                "relation_type": "SUPERSEDES",
                "target_hint": target_str,
                "span": preamble_window[span_start:span_end].strip(),
                "char_start": m.start(),
                "char_end": m.end(),
                "confidence": conf,
                "extractor": "regex",
                "rule": rule_name
            })
            break

    # 1c. INCORPORATES: "is incorporated by reference", "incorporated herein by reference"
    incorporates_patterns = [
        (
            r"([a-z0-9\s\.\-]+?)\s+(?:is|are)\s+(?:hereby\s+)?incorporated\s+(?:herein\s+)?by\s+reference",
            "preamble_incorporated_by_reference",
            0.92
        ),
        (
            r"incorporated\s+by\s+reference\s+into\s+(?:this\s+)?([a-z0-9\s]+?)(?=\.|\;|\,)",
            "preamble_incorporated_into",
            0.90
        )
    ]
    for pattern, rule_name, conf in incorporates_patterns:
        m = re.search(pattern, preamble_lower)
        if m:
            target_str = (m.group(1) or "Agreement").strip()
            span_start = max(0, m.start() - 10)
            span_end = min(len(preamble_window), m.end() + 30)
            detected_cues.append({
                "relation_type": "INCORPORATES",
                "target_hint": target_str,
                "span": preamble_window[span_start:span_end].strip(),
                "char_start": m.start(),
                "char_end": m.end(),
                "confidence": conf,
                "extractor": "regex",
                "rule": rule_name
            })
            break

    # 1d. CARVES_OUT: "except as set forth in Exhibit...", "carves out...", "subject to Section..."
    carve_out_patterns = [
        (
            r"except\s+(?:as\s+(?:expressly\s+)?set\s+forth\s+in\s+)?(?:exhibit|schedule|section|clause|addendum)\s*([a-z0-9\.\-]+)",
            "preamble_except_as_set_forth",
            0.88
        ),
        (
            r"carves?\s+out\s+(?:of\s+)?(?:the\s+terms\s+of\s+)?([a-z0-9\s]+?)(?=\.|\;|\,)",
            "preamble_carves_out_explicit",
            0.91
        ),
        (
            r"subject\s+to\s+(?:the\s+carve-?out\s+in\s+)?(?:exhibit|schedule|section)\s*([a-z0-9\.\-]+)",
            "preamble_subject_to_carveout",
            0.86
        )
    ]
    for pattern, rule_name, conf in carve_out_patterns:
        m = re.search(pattern, preamble_lower)
        if m:
            target_str = (m.group(1) or "Exhibit").strip()
            span_start = max(0, m.start() - 10)
            span_end = min(len(preamble_window), m.end() + 30)
            detected_cues.append({
                "relation_type": "CARVES_OUT",
                "target_hint": target_str,
                "span": preamble_window[span_start:span_end].strip(),
                "char_start": m.start(),
                "char_end": m.end(),
                "confidence": conf,
                "extractor": "regex",
                "rule": rule_name
            })
            break

    # 1e. SCHEDULE_OF: "statement of work entered into pursuant to...", "governed by the terms of the MSA"
    sow_patterns = [
        (
            r"(?:statement\s+of\s+work|sow)\s*(?:no\.?\s*(\d+|[a-z]+))?\s*(?:is\s+entered\s+into\s+pursuant\s+to|governed\s+by\s+(?:the\s+terms\s+of)?|under)\s+(?:that\s+certain\s+)?([a-z0-9\s]+?)(?=\s+dated|\s+by\s+and\s+between|\s+entered|\.|\;|\,)",
            "preamble_sow_pursuant_to",
            0.95
        ),
        (
            r"this\s+schedule\s+is\s+governed\s+by\s+(?:the\s+terms\s+of\s+)?([a-z0-9\s]+?)(?=\.|\;|\,)",
            "preamble_schedule_governed_by",
            0.91
        )
    ]
    for pattern, rule_name, conf in sow_patterns:
        m = re.search(pattern, preamble_lower)
        if m:
            target_str = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else m.group(1)
            target_str = (target_str or "Master Services Agreement").strip()
            span_start = max(0, m.start() - 10)
            span_end = min(len(preamble_window), m.end() + 30)
            detected_cues.append({
                "relation_type": "SCHEDULE_OF",
                "target_hint": target_str,
                "span": preamble_window[span_start:span_end].strip(),
                "char_start": m.start(),
                "char_end": m.end(),
                "confidence": conf,
                "extractor": "regex",
                "rule": rule_name
            })
            break

    # -------------------------------------------------------------------------
    # 2. Filename Cues (Fallback & Reinforcement)
    # -------------------------------------------------------------------------
    fn_amend = re.search(r"amendment[_\s]*(?:no\.?|#)?[_\s]*(\d+|[a-z]+)?[_\s]*(?:to|of)[_\s]*([a-z0-9_\s\-]+?)(?:\.[a-z0-9]+)?$", fn_lower)
    if fn_amend:
        detected_cues.append({
            "relation_type": "AMENDS",
            "target_hint": fn_amend.group(2).replace("_", " ").strip(),
            "span": f"Filename cue: '{filename}'",
            "confidence": 0.85,
            "extractor": "regex",
            "rule": "filename_amendment"
        })

    fn_sow = re.search(r"(?:sow|statement[_\s]+of[_\s]+work)[_\s]*(?:no\.?|#)?[_\s]*(\d+|[a-z]+)?[_\s]*(?:under|to|for)?[_\s]*([a-z0-9_\s\-]+?)(?:\.[a-z0-9]+)?$", fn_lower)
    if fn_sow:
        detected_cues.append({
            "relation_type": "SCHEDULE_OF",
            "target_hint": fn_sow.group(2).replace("_", " ").strip() or "msa",
            "span": f"Filename cue: '{filename}'",
            "confidence": 0.85,
            "extractor": "regex",
            "rule": "filename_sow"
        })

    if "restated" in fn_lower or "superseding" in fn_lower:
        detected_cues.append({
            "relation_type": "SUPERSEDES",
            "target_hint": filename,
            "span": f"Filename cue: '{filename}'",
            "confidence": 0.80,
            "extractor": "regex",
            "rule": "filename_restated"
        })

    # -------------------------------------------------------------------------
    # 3. Clause Scope Detection (e.g. "Section 4.1", "ALL")
    # -------------------------------------------------------------------------
    clause_scope = "ALL"
    scope_span = ""
    scope_match = re.search(r"(?:section|clause|article|§)\s*([\d\.\-]+)\s+(?:of\s+the\s+agreement\s+)?is\s+hereby\s+amended", preamble_lower)
    if not scope_match:
        scope_match = re.search(r"amends?\s+(?:section|clause|article|§)\s*([\d\.\-]+)", preamble_lower)
    if scope_match:
        clause_scope = f"Section {scope_match.group(1)}"
        scope_start = max(0, scope_match.start() - 10)
        scope_end = min(len(preamble_window), scope_match.end() + 60)
        scope_span = preamble_window[scope_start:scope_end].strip()

    # -------------------------------------------------------------------------
    # 4. Target Resolution Against Existing Agreements in Database
    # -------------------------------------------------------------------------
    existing_agreements = db.query(Agreement).filter(
        Agreement.tenant_id == tenant_id
    ).all()

    # Prioritize higher confidence preamble cues over filename cues
    detected_cues.sort(key=lambda c: c.get("confidence", 0.0), reverse=True)
    seen_dedup = set()

    for cue in detected_cues:
        rel_type = cue["relation_type"]
        hint = cue.get("target_hint", "").lower()
        tokens = normalize_title_tokens(hint)

        best_target = None
        best_score = 0

        for ag in existing_agreements:
            if source_ag_id is not None and ag.id == source_ag_id:
                continue

            ag_tokens = normalize_title_tokens(ag.title)
            score = 0

            # MSA shorthand matching
            if "msa" in tokens and ("msa" in ag_tokens or "master" in ag_tokens):
                score += 5
            if "sow" in tokens and "statement" in ag_tokens:
                score += 5

            # Token overlap
            overlap = set(tokens).intersection(set(ag_tokens))
            score += len(overlap) * 2

            if score > best_score:
                best_score = score
                best_target = ag

        # Require reasonable confidence score match or default to single MSA if unambiguous
        if not best_target and len(existing_agreements) == 1 and existing_agreements[0].id != source_ag_id:
            best_target = existing_agreements[0]
            best_score = 1

        if best_target and best_score >= 1:
            dedup_key = (source_ag_id, best_target.id, rel_type, clause_scope)
            if dedup_key in seen_dedup:
                continue
            seen_dedup.add(dedup_key)

            combined_span = cue.get("span", "")
            if scope_span and scope_span not in combined_span and clause_scope != "ALL":
                combined_span = f"{combined_span}. {scope_span}"

            candidate_edge = {
                "source_agreement_id": source_ag_id,
                "target_agreement_id": best_target.id,
                "target_agreement_title": best_target.title,
                "relation_type": rel_type,
                "clause_scope": clause_scope,
                "extractor": cue.get("extractor", "regex"),
                "confidence": cue.get("confidence", 0.85),
                "span": combined_span,
                "source_excerpt": combined_span,
                "status": "proposed",
                "notes": f"Detected via {cue.get('rule', 'pattern')} targeting '{best_target.title}'."
            }

            # Optional persistence with proposed status
            if auto_persist_proposed and source_ag_id is not None:
                # Check if exact unique relation already exists
                existing_rel = db.query(AgreementRelation).filter(
                    AgreementRelation.tenant_id == tenant_id,
                    AgreementRelation.source_agreement_id == source_ag_id,
                    AgreementRelation.target_agreement_id == best_target.id,
                    AgreementRelation.relation_type == rel_type
                ).first()

                if not existing_rel:
                    rel_record = AgreementRelation(
                        tenant_id=tenant_id,
                        source_agreement_id=source_ag_id,
                        target_agreement_id=best_target.id,
                        relation_type=rel_type,
                        clause_scope=clause_scope,
                        extractor=candidate_edge["extractor"],
                        confidence=candidate_edge["confidence"],
                        span=candidate_edge["span"],
                        status="proposed",
                        notes=candidate_edge["notes"]
                    )
                    db.add(rel_record)
                    db.flush()
                    candidate_edge["relation_id"] = rel_record.id
                else:
                    candidate_edge["relation_id"] = existing_rel.id
                    candidate_edge["status"] = existing_rel.status

            candidates.append(candidate_edge)

    return candidates


def accept_relation_edge(
    db: Session,
    relation_id: int,
    tenant_id: str = "org_default"
) -> dict[str, Any]:
    """
    Human-in-the-loop review: Accept a proposed relation edge, making it operative in graph walks.
    """
    rel = db.query(AgreementRelation).filter(
        AgreementRelation.id == relation_id,
        AgreementRelation.tenant_id == tenant_id
    ).first()
    if not rel:
        raise ValueError(f"AgreementRelation #{relation_id} not found for tenant '{tenant_id}'.")

    rel.status = "accepted"
    db.commit()
    logger.info(f"Accepted AgreementRelation #{relation_id} ({rel.relation_type}): {rel.source_agreement_id} -> {rel.target_agreement_id}")
    return {
        "status": "success",
        "relation_id": rel.id,
        "new_status": "accepted",
        "relation_type": rel.relation_type
    }


def reject_relation_edge(
    db: Session,
    relation_id: int,
    tenant_id: str = "org_default"
) -> dict[str, Any]:
    """
    Human-in-the-loop review: Reject a proposed relation edge. It is marked rejected and ignored by resolver.
    """
    rel = db.query(AgreementRelation).filter(
        AgreementRelation.id == relation_id,
        AgreementRelation.tenant_id == tenant_id
    ).first()
    if not rel:
        raise ValueError(f"AgreementRelation #{relation_id} not found for tenant '{tenant_id}'.")

    rel.status = "rejected"
    db.commit()
    logger.info(f"Rejected AgreementRelation #{relation_id} ({rel.relation_type}): {rel.source_agreement_id} -> {rel.target_agreement_id}")
    return {
        "status": "success",
        "relation_id": rel.id,
        "new_status": "rejected",
        "relation_type": rel.relation_type
    }
