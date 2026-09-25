"""
src/backend/resolver.py
=======================
Controlling-document resolver and commercial conflict detection engine.
Implements a true Directed Acyclic Graph (DAG) walk across agreement relations:
  - AMENDS: scope-aware amendment chains with structured slot inheritance
  - SUPERSEDES: full or scoped retirement of instruments with recursive transitive closure
  - SCHEDULE_OF: statement of work hierarchy with topic-level precedence (controls_for)
  - INCORPORATES: incorporation by reference into governing authority set
  - CARVES_OUT: exception qualification narrowing liability/indemnity without false peer ambiguity

Enforces strict party isolation (zero tenant fallback), UTC date-only comparisons,
cycle detection (depth cap 32), and dynamic confidence scoring.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .db import Agreement, AgreementRelation, Clause, ResolutionTraceRecord
from .taxonomy import get_slot_val

logger = logging.getLogger("kruschbiz.resolver")


# Topics where a Statement of Work (SOW) canonically controls over a Master Agreement (MSA)
SOW_CONTROLLING_TOPICS = {
    "PAYMENT_TERMS",
    "FEES",
    "DELIVERABLES",
    "PROJECT_SCOPE",
    "PRICING",
    "INVOICING",
    "HOURLY_RATES",
    "EXPENSES",
}

# Topics where a Master Agreement (MSA) canonically controls over a Statement of Work (SOW)
MSA_CONTROLLING_TOPICS = {
    "LIMITATION_OF_LIABILITY",
    "LIABILITY_CAP",
    "INDEMNITY",
    "INDEMNIFICATION",
    "GOVERNING_LAW",
    "DATA_PROTECTION",
    "CONFIDENTIALITY",
    "INTELLECTUAL_PROPERTY",
    "WARRANTY",
    "WARRANTIES",
    "FORCE_MAJEURE",
    "DISPUTE_RESOLUTION",
}

TOPIC_ALIASES: dict[str, list[str]] = {
    "SLA_UPTIME": ["SLA_UPTIME", "SLA_PERFORMANCE"],
    "SLA_PERFORMANCE": ["SLA_PERFORMANCE", "SLA_UPTIME"],
    "LIMITATION_OF_LIABILITY": ["LIMITATION_OF_LIABILITY", "LIABILITY_CAP"],
    "LIABILITY_CAP": ["LIABILITY_CAP", "LIMITATION_OF_LIABILITY"],
    "INDEMNITY": ["INDEMNITY", "INDEMNIFICATION"],
    "INDEMNIFICATION": ["INDEMNIFICATION", "INDEMNITY"],
    "TERMINATION": ["TERMINATION", "TERMINATION_CONVENIENCE"],
    "TERMINATION_CONVENIENCE": ["TERMINATION_CONVENIENCE", "TERMINATION"],
}


def normalize_party_name(name: str | None) -> str:
    """Normalize corporate legal name for strict deterministic matching."""
    if not name:
        return ""
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[,\.\(\)]", " ", cleaned)
    cleaned = re.sub(
        r"\b(inc|incorporated|llc|corp|corporation|ltd|limited|co|company|lp|llp|gmbh|sa|plc)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_party_match(party_a: str | None, party_b: str | None) -> bool:
    """Check if two counterparty strings identify the exact same entity."""
    if not party_a or not party_b:
        return False
    norm_a = normalize_party_name(party_a)
    norm_b = normalize_party_name(party_b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    min_len = min(len(norm_a), len(norm_b))
    if min_len >= 4 and (norm_a in norm_b or norm_b in norm_a):
        return True
    return False


def to_utc_date(val: Any) -> date:
    """Normalize input date or datetime to a date-only UTC representation."""
    if val is None:
        return datetime.now(timezone.utc).date()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        val_clean = val.strip()
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", val_clean)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        try:
            return datetime.fromisoformat(val_clean.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


def normalize_section(section: str | None) -> str:
    """Normalize section locator string (e.g. 'Section 4.1', 'Section 6.', '§4.1', '4.1' -> '4.1')."""
    if not section:
        return ""
    cleaned = section.strip().lower()
    cleaned = re.sub(r"^(?:section|clause|schedule|article|exhibit|§)\s*", "", cleaned)
    return cleaned.strip(" .:")


def compute_clause_uid(
    instrument_family: str,
    canonical_topic: str,
    slot_signature: dict[str, Any] | None = None,
    restates_clause_id: int | None = None
) -> str:
    """
    Deterministic stable clause UID based on:
    hash(instrument_family, canonical_topic, slot_signature, restates_clause_id)
    """
    family = normalize_party_name(instrument_family)
    topic = canonical_topic.strip().upper()
    sig_str = ""
    if slot_signature:
        clean_slots = {k: get_slot_val(v) for k, v in sorted(slot_signature.items()) if get_slot_val(v) is not None}
        sig_str = json.dumps(clean_slots, sort_keys=True)
    payload = f"{family}|{topic}|{sig_str}|{restates_clause_id or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def is_scope_match(scope_obj: Any, clause: Clause, topic: str) -> bool:
    """
    Verify if a relation's scope governs a specific clause or topic.
    Supports structured scope attributes (scope_type, scope_topics, scope_sections) on AgreementRelation,
    as well as string clause_scope. Enforces strict exact normalized section matching so 'Section 4'
    cannot falsely govern 'Section 4.2'.
    """
    if scope_obj is None:
        return True

    # 1. Structured Scope Evaluation on AgreementRelation model
    if hasattr(scope_obj, "scope_type"):
        s_type = (getattr(scope_obj, "scope_type", None) or "ALL").upper()
        if s_type in ("ALL", "*"):
            return True
        if s_type == "TOPICS":
            t_list = [t.upper() for t in (getattr(scope_obj, "scope_topics", []) or [])]
            return topic.upper() in t_list
        if s_type == "SECTIONS":
            sec_list = [normalize_section(s) for s in (getattr(scope_obj, "scope_sections", []) or [])]
            c_sec = normalize_section(clause.section)
            return bool(c_sec and c_sec in sec_list)
        if s_type == "EXHIBITS":
            ex_list = [ex.lower() for ex in (getattr(scope_obj, "scope_exhibits", []) or [])]
            c_sec_raw = (clause.section or "").lower()
            c_title_raw = (clause.title or "").lower()
            return any(ex in c_sec_raw or ex in c_title_raw for ex in ex_list)
        clause_scope = getattr(scope_obj, "clause_scope", None)
    elif isinstance(scope_obj, str):
        clause_scope = scope_obj
    else:
        clause_scope = None

    if not clause_scope or clause_scope.strip().upper() in ("ALL", "*"):
        return True

    scope = clause_scope.strip().lower()

    # Topic-level scope, e.g. "topic:PAYMENT_TERMS" or "PAYMENT_TERMS"
    if scope.startswith("topic:"):
        scope_topic = scope.split("topic:", 1)[1].strip().upper()
        return scope_topic == topic.upper()
    if scope.upper() == topic.upper():
        return True

    # Section-level scope: Strict normalized exact match prevents '4' matching '4.2'
    if clause.section:
        c_sec = clause.section.strip().lower()
        if scope == c_sec:
            return True
        norm_scope = normalize_section(scope)
        norm_c_sec = normalize_section(c_sec)
        if norm_scope and norm_scope == norm_c_sec:
            return True

    # Check if clause title matches scope
    if clause.title and scope == clause.title.strip().lower():
        return True

    return False


def get_party_agreements(db: Session, tenant_id: str, counterparty: str) -> list[Agreement]:
    """
    Fetch agreements for a strictly matched counterparty entity or alias.
    Resolves canonical Party entity and PartyAlias records if present.
    STRICT SECURITY INVARIANT: Zero fallback to all tenant agreements.
    """
    from .db import Party, PartyAlias

    norm_target = normalize_party_name(counterparty)

    # 1. Check if counterparty matches a first-class Party entity or PartyAlias
    party = db.query(Party).filter(
        Party.tenant_id == tenant_id,
        (Party.canonical_name.ilike(counterparty.strip()) |
         Party.canonical_name.ilike(norm_target))
    ).first()

    if not party:
        alias = db.query(PartyAlias).filter(
            PartyAlias.tenant_id == tenant_id,
            (PartyAlias.alias_name.ilike(counterparty.strip()) |
             PartyAlias.alias_name.ilike(norm_target))
        ).first()
        if alias:
            party = alias.party

    all_agreements = db.query(Agreement).filter(
        Agreement.tenant_id == tenant_id
    ).all()

    matched = []
    for ag in all_agreements:
        # Match via first-class Party entity link
        if party and ag.party_id is not None and ag.party_id == party.id:
            matched.append(ag)
            continue
        # Match via party aliases if party entity exists
        if party and ag.counterparty:
            if any(is_party_match(ag.counterparty, a.alias_name) for a in party.aliases):
                matched.append(ag)
                continue
            if is_party_match(ag.counterparty, party.canonical_name):
                matched.append(ag)
                continue
        # Standard strict normalized string matching
        if is_party_match(ag.counterparty, counterparty):
            matched.append(ag)

    return matched


def get_transitive_superseded(
    valid_relations: list[AgreementRelation],
    active_ag_ids: set[int],
    ag_by_id: dict[int, Agreement] | None = None,
    depth_cap: int = 32
) -> tuple[set[int], list[tuple[int, str]], bool]:
    """
    Recursively close the SUPERSEDES relation graph with cycle detection.
    Enforces the invariant: Draft instruments cannot supersede executed instruments.
    Returns (fully_superseded_ag_ids, scoped_superseded_tuples, cycle_detected).
    """
    fully_superseded: set[int] = set()
    scoped_superseded: list[tuple[int, str]] = []
    cycle_detected = False

    # Map source -> list of SUPERSEDES relations
    supersedes_by_source: dict[int, list[AgreementRelation]] = {}
    for r in valid_relations:
        if r.relation_type == "SUPERSEDES":
            supersedes_by_source.setdefault(r.source_agreement_id, []).append(r)

    # Queue starts with active surviving sources
    queue = list(active_ag_ids)
    visited_sources = set()
    depth = 0

    while queue and depth < depth_cap:
        depth += 1
        current_source = queue.pop(0)
        if current_source in visited_sources:
            cycle_detected = True
            continue
        visited_sources.add(current_source)

        for edge in supersedes_by_source.get(current_source, []):
            target = edge.target_agreement_id

            # Invariant: Unexecuted draft cannot supersede executed agreement
            if ag_by_id:
                src_ag = ag_by_id.get(current_source)
                tgt_ag = ag_by_id.get(target)
                if src_ag and tgt_ag:
                    if getattr(src_ag, "execution_status", "executed") == "draft" and getattr(tgt_ag, "execution_status", "executed") != "draft":
                        logger.info(f"Skipping SUPERSEDES edge: draft agreement {src_ag.id} cannot supersede executed {tgt_ag.id}")
                        continue

            if not edge.clause_scope or edge.clause_scope.strip().upper() in ("ALL", "*"):
                if target not in fully_superseded:
                    fully_superseded.add(target)
                    queue.append(target)
            else:
                scoped_superseded.append((target, edge.clause_scope))

    if depth >= depth_cap and queue:
        cycle_detected = True

    return fully_superseded, scoped_superseded, cycle_detected


def _persist_trace_record(
    db: Session,
    tenant_id: str,
    counterparty: str,
    topic: str,
    as_of: Any,
    result_dict: dict[str, Any]
) -> None:
    """
    Persist an immutable ResolutionTraceRecord to database audit log.
    Includes evaluated hops, winning clauses, defeated candidates, and rejection rationale.
    """
    try:
        winner = result_dict.get("controlling_clause")
        winner_ag_id = winner.get("agreement_id") if isinstance(winner, dict) else None
        winner_cl_id = winner.get("id") if isinstance(winner, dict) else None

        trace_id = str(uuid.uuid4())
        trace_payload = {
            "trace_id": trace_id,
            "as_of_date": str(as_of),
            "counterparty": counterparty,
            "topic": topic,
            "status": result_dict.get("status"),
            "controlling_clause_id": winner_cl_id,
            "controlling_agreement_id": winner_ag_id,
            "confidence": result_dict.get("confidence", 0.0),
            "resolution_rationale": result_dict.get("resolution_rationale"),
            "amendment_trail": result_dict.get("amendment_trail", []),
            "proposed_relations_advisory": result_dict.get("proposed_relations_advisory", []),
            "conflicting_candidates": result_dict.get("conflicting_candidates", []),
        }
        result_dict["resolution_trace"] = trace_payload

        trace_rec = ResolutionTraceRecord(
            id=trace_id,
            tenant_id=tenant_id,
            counterparty=counterparty,
            topic=topic,
            as_of_date=str(as_of),
            status=result_dict.get("status") or "unknown",
            controlling_agreement_id=winner_ag_id,
            controlling_clause_id=winner_cl_id,
            confidence=result_dict.get("confidence", 0.0),
            resolution_rationale=result_dict.get("resolution_rationale"),
            trace_payload=trace_payload
        )
        db.add(trace_rec)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"Could not persist ResolutionTraceRecord: {exc}")


def compute_resolution_confidence(
    trail: list[dict[str, Any]],
    has_competing_peers: bool = False,
    missing_dates: bool = False,
    is_keyword_fallback: bool = False,
    cycle_detected: bool = False,
    base_confidence: float = 0.85
) -> float:
    """
    Compute dynamic, non-hardcoded confidence for a resolved controlling clause.
    Deducts for missing dates, keyword fallback, or cycles. Zero on unresolved conflicts.
    """
    if has_competing_peers:
        return 0.0

    conf = 1.0 if trail else base_confidence

    if missing_dates:
        conf -= 0.15
    if is_keyword_fallback:
        conf -= 0.20
    if cycle_detected:
        conf -= 0.25

    return max(0.1, min(1.0, round(conf, 2)))


def resolve_controlling_clause(
    db: Session,
    tenant_id: str,
    counterparty: str,
    topic: str,
    as_of_date: Any = None
) -> dict[str, Any]:
    """
    Resolve which contract clause controls for a given topic as of a specific date.
    Implements a true DAG graph walk:
      1. Resolves party identity (strict matching, zero tenant fallback).
      2. Enforces UTC date-only temporal validity (effective <= as_of, not expired).
      3. Recursively prunes full and scoped SUPERSEDES chains (A -> B -> C transitive closure).
      4. Pulls INCORPORATES edges into candidate authority sets.
      5. Traverses inbound AMENDS edges to leaf amendments with structured slot inheritance.
      6. Evaluates SOW vs MSA order of precedence when multiple instruments survive.
      7. Attaches CARVES_OUT qualifications to narrow obligations without false ambiguity.
      8. Computes dynamic confidence and returns comprehensive amendment_trail audit artifact.
    """
    as_of = to_utc_date(as_of_date)
    proposed_relations_advisory: list[dict[str, Any]] = []

    def _finalize_result(result_dict: dict[str, Any]) -> dict[str, Any]:
        result_dict["proposed_relations_advisory"] = proposed_relations_advisory
        _persist_trace_record(db, tenant_id, counterparty, topic, as_of, result_dict)
        return result_dict

    # 1. Fetch agreements for counterparty (STRICT ZERO FALLBACK)
    agreements = get_party_agreements(db, tenant_id, counterparty)
    if not agreements:
        return _finalize_result({
            "status": "not_found",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"No commercial agreements found for counterparty '{counterparty}'.",
            "confidence": 0.0
        })

    ag_by_id = {ag.id: ag for ag in agreements}
    ag_ids = list(ag_by_id.keys())

    # 2. Check temporal validity of agreements
    active_ag_ids = set()
    missing_dates = False

    for ag in agreements:
        if ag.status in ("terminated", "expired", "archived"):
            continue
        eff_start = getattr(ag, "effective_from", None) or ag.effective_date or getattr(ag, "execution_date", None)
        if eff_start is None:
            missing_dates = True
        elif to_utc_date(eff_start) > as_of:
            continue
        eff_end = getattr(ag, "effective_to", None) or getattr(ag, "termination_date", None) or ag.expiration_date
        if eff_end and to_utc_date(eff_end) <= as_of:
            continue
        active_ag_ids.add(ag.id)

    # 3. Load relations operative as of as_of_date
    relations = db.query(AgreementRelation).filter(
        AgreementRelation.tenant_id == tenant_id,
        or_(
            AgreementRelation.source_agreement_id.in_(ag_ids),
            AgreementRelation.target_agreement_id.in_(ag_ids)
        )
    ).all()

    valid_relations: list[AgreementRelation] = []
    for rel in relations:
        rel_status = getattr(rel, "status", "accepted")
        if rel_status == "rejected":
            continue
        if rel_status == "proposed":
            # Invariant: Auto-extracted proposed edges NEVER silently control the precedence DAG!
            proposed_relations_advisory.append({
                "relation_id": rel.id,
                "relation_type": rel.relation_type,
                "source_agreement_id": rel.source_agreement_id,
                "target_agreement_id": rel.target_agreement_id,
                "clause_scope": rel.clause_scope,
                "confidence": getattr(rel, "confidence", 1.0),
                "status": "proposed",
                "notes": rel.notes
            })
            continue
        if rel.effective_date and to_utc_date(rel.effective_date) > as_of:
            continue
        valid_relations.append(rel)

    # 4. Transitive SUPERSEDES Recursive Closure
    fully_superseded_ag_ids, scoped_superseded, supersedes_cycle = get_transitive_superseded(
        valid_relations=valid_relations,
        active_ag_ids=active_ag_ids,
        ag_by_id=ag_by_id,
        depth_cap=32
    )

    surviving_ag_ids = [aid for aid in active_ag_ids if aid not in fully_superseded_ag_ids]

    if not surviving_ag_ids:
        return _finalize_result({
            "status": "all_authorities_superseded",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"All agreements for counterparty '{counterparty}' are superseded or expired as of {as_of}.",
            "confidence": 0.0
        })

    # 5. Fetch candidate clauses matching topic
    is_keyword_fallback = False
    topic_candidates = TOPIC_ALIASES.get(topic, [topic])
    candidate_clauses = db.query(Clause).filter(
        Clause.tenant_id == tenant_id,
        Clause.agreement_id.in_(ag_ids),
        Clause.is_active.is_(True),
        Clause.topic.in_(topic_candidates)
    ).all()

    if not candidate_clauses:
        topic_kw = topic.replace("_", " ").lower()
        candidate_clauses = db.query(Clause).filter(
            Clause.tenant_id == tenant_id,
            Clause.agreement_id.in_(ag_ids),
            Clause.is_active.is_(True),
            or_(
                Clause.content.ilike(f"%{topic_kw}%"),
                Clause.title.ilike(f"%{topic_kw}%")
            )
        ).all()
        if candidate_clauses:
            is_keyword_fallback = True

    if not candidate_clauses:
        return _finalize_result({
            "status": "topic_not_found",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"No clauses found addressing topic '{topic}' across agreements for '{counterparty}'.",
            "confidence": 0.0
        })

    # Index relations by target agreement for fast AMENDS lookup
    amends_by_target: dict[int, list[AgreementRelation]] = {}
    for rel in valid_relations:
        if rel.relation_type == "AMENDS":
            amends_by_target.setdefault(rel.target_agreement_id, []).append(rel)

    # Deduplicate candidate clauses per agreement before graph traversal:
    # Prefer substantive clauses (with structured slots or longer content) over empty section headings
    deduped_candidates: list[Clause] = []
    clauses_by_ag: dict[int, list[Clause]] = {}
    for c in candidate_clauses:
        clauses_by_ag.setdefault(c.agreement_id, []).append(c)
    for ag_id, c_list in clauses_by_ag.items():
        if len(c_list) == 1:
            deduped_candidates.append(c_list[0])
        else:
            c_list.sort(key=lambda c: (len(c.structured_slots or {}), len(c.content or "")), reverse=True)
            deduped_candidates.append(c_list[0])
    candidate_clauses = deduped_candidates

    # 6. Clause Graph Traversal with Slot Inheritance & Depth Cap
    terminal_candidates: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
    amended_clause_ids = set()
    amends_cycle_detected = False

    for base_clause in candidate_clauses:
        if base_clause.agreement_id in fully_superseded_ag_ids:
            continue

        # Check scoped supersession
        is_scoped_out = False
        for sup_ag_id, sup_scope in scoped_superseded:
            if base_clause.agreement_id == sup_ag_id and is_scope_match(sup_scope, base_clause, topic):
                is_scoped_out = True
                break
        if is_scoped_out:
            continue

        # Walk AMENDS edges forward from this base clause
        trail: list[dict[str, Any]] = []
        current_clause = base_clause
        effective_slots = dict(base_clause.structured_slots or {})
        visited_clauses = {current_clause.id}
        depth = 0

        while depth < 32:
            depth += 1
            current_ag_id = current_clause.agreement_id
            incoming_amendments = list(amends_by_target.get(current_ag_id, []))

            # Order by effective date ascending to step forward temporally
            def _rel_eff_date(r: AgreementRelation) -> date:
                if r.effective_date:
                    return to_utc_date(r.effective_date)
                src_ag = ag_by_id.get(r.source_agreement_id)
                if src_ag and src_ag.effective_date:
                    return to_utc_date(src_ag.effective_date)
                return date.min

            incoming_amendments.sort(key=_rel_eff_date)

            found_next = False
            for rel in incoming_amendments:
                if rel.source_agreement_id not in active_ag_ids or rel.source_agreement_id in fully_superseded_ag_ids:
                    continue

                # Check if amending source is scoped superseded for this topic
                is_src_scoped_out = False
                for sup_ag_id, sup_scope in scoped_superseded:
                    if rel.source_agreement_id == sup_ag_id and is_scope_match(sup_scope, current_clause, topic):
                        is_src_scoped_out = True
                        break
                if is_src_scoped_out:
                    continue

                # Invariant: Draft agreement cannot amend executed agreement
                src_ag = ag_by_id.get(rel.source_agreement_id)
                tgt_ag = ag_by_id.get(current_clause.agreement_id)
                if src_ag and tgt_ag:
                    if getattr(src_ag, "execution_status", "executed") == "draft" and getattr(tgt_ag, "execution_status", "executed") != "draft":
                        logger.info(f"Skipping AMENDS edge: draft {src_ag.id} cannot amend executed {tgt_ag.id}")
                        continue

                if not is_scope_match(rel.clause_scope, current_clause, topic):
                    continue

                # Fetch amending clauses in the source agreement
                source_clauses = clauses_by_ag.get(rel.source_agreement_id, [])
                if not source_clauses:
                    source_clauses = db.query(Clause).filter(
                        Clause.tenant_id == tenant_id,
                        Clause.agreement_id == rel.source_agreement_id,
                        Clause.is_active.is_(True),
                        or_(Clause.topic == topic, Clause.section.isnot(None))
                    ).all()

                matching_amending_clause = None
                for sc in source_clauses:
                    if sc.topic == topic or is_scope_match(rel.clause_scope, sc, topic):
                        matching_amending_clause = sc
                        break

                if matching_amending_clause and matching_amending_clause.id not in visited_clauses:
                    visited_clauses.add(matching_amending_clause.id)
                    amended_clause_ids.add(current_clause.id)

                    # Slot inheritance: overlay amended slots onto inherited base slots
                    amd_slots = dict(matching_amending_clause.structured_slots or {})
                    overridden_keys = [k for k in amd_slots.keys() if k in effective_slots]
                    inherited_keys = [k for k in effective_slots.keys() if k not in amd_slots]
                    effective_slots.update(amd_slots)

                    trail.append({
                        "relation": "AMENDS",
                        "scope": rel.clause_scope or "ALL",
                        "from_agreement_id": current_clause.agreement_id,
                        "from_agreement_title": ag_by_id[current_clause.agreement_id].title if current_clause.agreement_id in ag_by_id else "Agreement",
                        "from_section": current_clause.section,
                        "to_agreement_id": matching_amending_clause.agreement_id,
                        "to_agreement_title": ag_by_id[matching_amending_clause.agreement_id].title if matching_amending_clause.agreement_id in ag_by_id else "Agreement",
                        "to_section": matching_amending_clause.section,
                        "effective_date": str(rel.effective_date) if rel.effective_date else None,
                        "inherited_slots": inherited_keys,
                        "overridden_slots": overridden_keys,
                    })

                    current_clause = matching_amending_clause
                    found_next = True
                    break
                elif matching_amending_clause and matching_amending_clause.id in visited_clauses:
                    amends_cycle_detected = True

            if not found_next:
                break

        if current_clause.agreement_id in surviving_ag_ids:
            # Check if current_clause was scoped superseded
            is_curr_scoped_out = False
            for sup_ag_id, sup_scope in scoped_superseded:
                if current_clause.agreement_id == sup_ag_id and is_scope_match(sup_scope, current_clause, topic):
                    is_curr_scoped_out = True
                    break
            if is_curr_scoped_out:
                continue

            # An amendment cannot stand as an independent peer against a governing agreement
            # unless reached via a valid relation trail.
            ag_curr = ag_by_id.get(current_clause.agreement_id)
            is_amendment_type = ag_curr and (
                ag_curr.instrument_type in ("amendment", "amendment_addendum", "rider", "addendum")
                or current_clause.authority_class in ("amendment", "amendment_addendum", "executed_amendment")
            )
            has_other_governing = any(
                ag_by_id[aid].instrument_type not in ("amendment", "amendment_addendum", "rider", "addendum")
                for aid in surviving_ag_ids if aid in ag_by_id
            )
            if is_amendment_type and len(trail) == 0 and has_other_governing:
                continue

            terminal_candidates.append((current_clause, trail, effective_slots))

    # Deduplicate terminal candidates by clause ID
    unique_terminals: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
    seen_terminal_ids = set()
    for cl, tr, sl in terminal_candidates:
        if cl.id not in seen_terminal_ids and cl.id not in amended_clause_ids:
            seen_terminal_ids.add(cl.id)
            unique_terminals.append((cl, tr, sl))

    if not unique_terminals and terminal_candidates:
        for cl, tr, sl in terminal_candidates:
            if cl.id not in seen_terminal_ids:
                seen_terminal_ids.add(cl.id)
                unique_terminals.append((cl, tr, sl))

    # Invariant: Unexecuted drafts cannot defeat executed agreements
    has_executed = any(
        getattr(ag_by_id.get(cl.agreement_id), "execution_status", "executed") != "draft"
        for cl, _, _ in unique_terminals
    )
    if has_executed:
        filtered_terminals = [
            (cl, tr, sl) for cl, tr, sl in unique_terminals
            if getattr(ag_by_id.get(cl.agreement_id), "execution_status", "executed") != "draft"
        ]
        if filtered_terminals:
            unique_terminals = filtered_terminals

    # Deduplicate candidate clauses belonging to the same agreement:
    # Prefer clauses with non-empty structured slots or longer substantive content over empty section headers
    by_ag: dict[int, list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]]] = {}
    for item in unique_terminals:
        by_ag.setdefault(item[0].agreement_id, []).append(item)

    deduped_by_ag: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
    for ag_id, cl_list in by_ag.items():
        if len(cl_list) == 1:
            deduped_by_ag.append(cl_list[0])
        else:
            cl_list.sort(key=lambda it: (len(it[2]), len(it[0].content or "")), reverse=True)
            deduped_by_ag.append(cl_list[0])
    unique_terminals = deduped_by_ag

    if not unique_terminals:
        return _finalize_result({
            "status": "all_authorities_superseded",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"All candidate clauses for topic '{topic}' were superseded or amended into inactive instruments.",
            "confidence": 0.0
        })

    # 7. Evaluate CARVES_OUT and INCORPORATES Relations (Narrowing Qualifications & Schedules)
    subordinate_relations = [r for r in valid_relations if r.relation_type in ("CARVES_OUT", "INCORPORATES")]
    if len(unique_terminals) > 1 and subordinate_relations:
        # Check if one candidate is a CARVES_OUT or INCORPORATED schedule/exhibit of the other
        pruned_terminals: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
        for cl, tr, sl in unique_terminals:
            is_subordinate_source = False
            for sr in subordinate_relations:
                if sr.source_agreement_id == cl.agreement_id:
                    # cl is from the carve-out / incorporated schedule instrument
                    is_subordinate_source = True
                    # Find the target terminal candidate to attach carve-out / schedule qualification
                    for target_cl, target_tr, target_sl in unique_terminals:
                        if target_cl.agreement_id == sr.target_agreement_id:
                            target_tr.append({
                                "relation": sr.relation_type,
                                "scope": sr.clause_scope or "ALL",
                                "from_agreement_id": cl.agreement_id,
                                "from_agreement_title": ag_by_id[cl.agreement_id].title if cl.agreement_id in ag_by_id else "Schedule / Carve-Out Instrument",
                                "from_section": cl.section,
                                "to_agreement_id": target_cl.agreement_id,
                                "to_agreement_title": ag_by_id[target_cl.agreement_id].title if target_cl.agreement_id in ag_by_id else "Governing Agreement",
                                "to_section": target_cl.section,
                                "effective_date": str(sr.effective_date) if sr.effective_date else None,
                            })
                            # Attach carve-out slot
                            co_val = target_sl.get("carve_outs") or []
                            if isinstance(co_val, list):
                                co_val.append(f"{sr.relation_type} in {cl.section}: {cl.content[:80]}")
                                target_sl["carve_outs"] = co_val
                            break
                    break
            if not is_subordinate_source:
                pruned_terminals.append((cl, tr, sl))

        if pruned_terminals:
            unique_terminals = pruned_terminals

    # 7b. Fail-Closed on Cycle Detection (Priority 3: Cycle is a data error, not a haircut)
    has_cycle = supersedes_cycle or amends_cycle_detected
    if has_cycle:
        cycle_type = "SUPERSEDES" if supersedes_cycle else "AMENDS"
        try:
            from .db import ContractConflictRecord
            conflict_rec = ContractConflictRecord(
                tenant_id=tenant_id,
                counterparty=counterparty,
                topic=topic,
                as_of_date=str(as_of) if as_of else "unspecified",
                conflict_type="GRAPH_CYCLE",
                missing_edge_type=cycle_type,
                details=f"Cycle defect detected in {cycle_type} relation chain for counterparty '{counterparty}'."
            )
            db.add(conflict_rec)
            db.commit()
        except Exception as exc:
            logger.warning(f"Could not persist ContractConflictRecord for GRAPH_CYCLE: {exc}")

        return _finalize_result({
            "status": "GRAPH_CYCLE",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"Data integrity error: Circular precedence dependency detected ({cycle_type} cycle). Precedence cannot be reliably determined.",
            "confidence": 0.0
        })

    # 8. Single Unambiguous Winner
    if len(unique_terminals) == 1:
        winner, trail, merged_slots = unique_terminals[0]
        ag_winner = ag_by_id.get(winner.agreement_id)

        confidence = compute_resolution_confidence(
            trail=trail,
            has_competing_peers=False,
            missing_dates=missing_dates,
            is_keyword_fallback=is_keyword_fallback,
            cycle_detected=False,
            base_confidence=0.85
        )

        if trail:
            rationale = (
                f"Resolved via explicit {len(trail)}-hop amendment DAG walk to '{winner.section}' "
                f"in '{ag_winner.title if ag_winner else 'Agreement'}'. Leaf node is controlling as of {as_of}."
            )
        else:
            rationale = (
                f"Resolved controlling terms from operative agreement '{ag_winner.title if ag_winner else 'Agreement'}' "
                f"({winner.section}). No conflicting amendments found."
            )

        return _finalize_result({
            "status": "resolved",
            "controlling_clause": {
                "id": winner.id,
                "agreement_id": winner.agreement_id,
                "agreement_title": ag_winner.title if ag_winner else "Governing Agreement",
                "section": winner.section,
                "title": winner.title,
                "topic": winner.topic,
                "structured_slots": merged_slots,
                "content": winner.content,
                "authority_class": winner.authority_class,
                "effective_date": str(ag_winner.effective_date) if ag_winner and ag_winner.effective_date else None,
            },
            "amendment_trail": trail,
            "resolution_rationale": rationale,
            "confidence": confidence
        })

    # 9. Multiple Surviving Candidates: Order of Precedence (SOW vs MSA via DealPlaybook)
    from .db import DealPlaybook
    playbook = db.query(DealPlaybook).filter(DealPlaybook.tenant_id == tenant_id).first()
    sow_topics = set(playbook.sow_controlling_topics) if (playbook and playbook.sow_controlling_topics) else SOW_CONTROLLING_TOPICS

    sow_candidate = None
    msa_candidate = None
    sow_trail = []
    msa_trail = []
    sow_slots = {}
    msa_slots = {}

    schedule_relations = [r for r in valid_relations if r.relation_type == "SCHEDULE_OF"]

    for cl, tr, sl in unique_terminals:
        ag = ag_by_id.get(cl.agreement_id)
        if not ag:
            continue
        is_sow = ag.instrument_type == "statement_of_work" or "SOW" in ag.title.upper()
        for sr in schedule_relations:
            if sr.source_agreement_id == ag.id:
                is_sow = True
                break

        if is_sow:
            sow_candidate = cl
            sow_trail = tr
            sow_slots = sl
        else:
            msa_candidate = cl
            msa_trail = tr
            msa_slots = sl

    if sow_candidate and msa_candidate and len(unique_terminals) == 2:
        if topic in sow_topics:
            winner = sow_candidate
            trail = list(sow_trail)
            ag_winner = ag_by_id.get(winner.agreement_id)
            trail.append({
                "relation": "SCHEDULE_OF",
                "scope": f"topic:{topic}",
                "from_agreement_id": msa_candidate.agreement_id,
                "from_agreement_title": ag_by_id[msa_candidate.agreement_id].title if msa_candidate.agreement_id in ag_by_id else "MSA",
                "to_agreement_id": winner.agreement_id,
                "to_agreement_title": ag_winner.title if ag_winner else "SOW",
                "effective_date": str(ag_winner.effective_date) if ag_winner and ag_winner.effective_date else None,
            })
            confidence = compute_resolution_confidence(
                trail=trail,
                has_competing_peers=False,
                missing_dates=missing_dates,
                is_keyword_fallback=is_keyword_fallback,
                cycle_detected=False,
                base_confidence=0.90
            )
            return _finalize_result({
                "status": "resolved",
                "controlling_clause": {
                    "id": winner.id,
                    "agreement_id": winner.agreement_id,
                    "agreement_title": ag_winner.title if ag_winner else "Statement of Work",
                    "section": winner.section,
                    "title": winner.title,
                    "topic": winner.topic,
                    "structured_slots": sow_slots,
                    "content": winner.content,
                    "authority_class": winner.authority_class,
                    "effective_date": str(ag_winner.effective_date) if ag_winner and ag_winner.effective_date else None,
                },
                "amendment_trail": trail,
                "resolution_rationale": (
                    f"Resolved via order of precedence: Statement of Work '{ag_winner.title if ag_winner else 'SOW'}' "
                    f"controls for scoped topic '{topic}' over Master Services Agreement."
                ),
                "confidence": confidence
            })
        else:
            winner = msa_candidate
            trail = list(msa_trail)
            ag_winner = ag_by_id.get(winner.agreement_id)
            trail.append({
                "relation": "SCHEDULE_OF",
                "scope": f"topic:{topic}",
                "from_agreement_id": sow_candidate.agreement_id,
                "from_agreement_title": ag_by_id[sow_candidate.agreement_id].title if sow_candidate.agreement_id in ag_by_id else "SOW",
                "to_agreement_id": winner.agreement_id,
                "to_agreement_title": ag_winner.title if ag_winner else "MSA",
                "effective_date": str(ag_winner.effective_date) if ag_winner and ag_winner.effective_date else None,
            })
            confidence = compute_resolution_confidence(
                trail=trail,
                has_competing_peers=False,
                missing_dates=missing_dates,
                is_keyword_fallback=is_keyword_fallback,
                cycle_detected=False,
                base_confidence=0.90
            )
            return _finalize_result({
                "status": "resolved",
                "controlling_clause": {
                    "id": winner.id,
                    "agreement_id": winner.agreement_id,
                    "agreement_title": ag_winner.title if ag_winner else "Master Agreement",
                    "section": winner.section,
                    "title": winner.title,
                    "topic": winner.topic,
                    "structured_slots": msa_slots,
                    "content": winner.content,
                    "authority_class": winner.authority_class,
                    "effective_date": str(ag_winner.effective_date) if ag_winner and ag_winner.effective_date else None,
                },
                "amendment_trail": trail,
                "resolution_rationale": (
                    f"Resolved via order of precedence: Master Services Agreement '{ag_winner.title if ag_winner else 'MSA'}' "
                    f"controls for general legal governance ('{topic}') over Statement of Work."
                ),
                "confidence": confidence
            })

    # 10. Concurrently Active Instruments Disagree: Return AMBIGUOUS
    conflicting_candidates_info = []
    for cl, tr, sl in unique_terminals:
        ag = ag_by_id.get(cl.agreement_id)
        conflicting_candidates_info.append({
            "clause_id": cl.id,
            "agreement_id": cl.agreement_id,
            "agreement_title": ag.title if ag else "Agreement",
            "section": cl.section,
            "structured_slots": sl,
            "effective_date": str(ag.effective_date) if ag and ag.effective_date else None,
            "content_snippet": cl.content[:150] + "..." if len(cl.content) > 150 else cl.content
        })

    cand_a = unique_terminals[0][0] if len(unique_terminals) > 0 else None
    cand_b = unique_terminals[1][0] if len(unique_terminals) > 1 else None
    try:
        from .db import ContractConflictRecord
        conflict_rec = ContractConflictRecord(
            tenant_id=tenant_id,
            counterparty=counterparty,
            topic=topic,
            as_of_date=str(as_of) if as_of else "unspecified",
            conflict_type="AMBIGUOUS_CONTROLLING_INSTRUMENT",
            candidate_a_agreement_id=cand_a.agreement_id if cand_a else None,
            candidate_a_clause_id=cand_a.id if cand_a else None,
            candidate_b_agreement_id=cand_b.agreement_id if cand_b else None,
            candidate_b_clause_id=cand_b.id if cand_b else None,
            missing_edge_type="SUPERSEDES / AMENDS",
            details=(
                f"Found {len(unique_terminals)} concurrently active candidate clauses for topic '{topic}' "
                f"without a governing amendment or precedence edge."
            )
        )
        db.add(conflict_rec)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(f"Could not persist ContractConflictRecord for AMBIGUOUS_CONTROLLING_INSTRUMENT: {exc}")

    return _finalize_result({
        "status": "ambiguous",
        "controlling_clause": None,
        "conflicting_candidates": conflicting_candidates_info,
        "amendment_trail": [tr for _, tr, _ in unique_terminals if tr],
        "resolution_rationale": (
            f"Ambiguous controlling terms: Found {len(unique_terminals)} concurrently active candidate clauses "
            f"for topic '{topic}' without a governing amendment or precedence edge between them."
        ),
        "confidence": 0.0
    })


def detect_contract_conflicts(
    db: Session,
    tenant_id: str,
    counterparty: str,
    as_of_date: Any = None
) -> list[dict[str, Any]]:
    """
    Scan for unresolved commercial conflicts across a counterparty's agreement portfolio.
    Runs POST-RESOLUTION:
      1. Resolves all topics present in active agreements using resolve_controlling_clause.
      2. If a topic returns 'ambiguous', flags as an active conflict.
      3. For surviving operative clauses across different agreements, identifies differing slot values.
    """
    as_of = to_utc_date(as_of_date)
    agreements = get_party_agreements(db, tenant_id, counterparty)
    if not agreements:
        return []

    ag_ids = [ag.id for ag in agreements]

    topics = db.query(Clause.topic).filter(
        Clause.tenant_id == tenant_id,
        Clause.agreement_id.in_(ag_ids),
        Clause.is_active.is_(True),
        Clause.topic != "GENERAL_COMMERCIAL"
    ).distinct().all()

    conflicts: list[dict[str, Any]] = []

    for (top,) in topics:
        res = resolve_controlling_clause(db, tenant_id, counterparty, top, as_of)
        if res.get("status") == "ambiguous":
            candidates = res.get("conflicting_candidates", [])
            conflicts.append({
                "topic": top,
                "conflict_type": "AMBIGUOUS_CONTROLLING_INSTRUMENT",
                "severity": "HIGH",
                "explanation": (
                    f"Topic '{top}' has {len(candidates)} concurrently active provisions with divergent obligations "
                    f"and no governing precedence edge."
                ),
                "candidates": candidates
            })

    return conflicts


def diff_agreements(
    db: Session,
    agreement_a_id: int,
    agreement_b_id: int,
    tenant_id: str = "org_default"
) -> dict[str, Any]:
    """
    Compare two legal instruments side-by-side:
      Alignment order:
        1. Explicit restatement pointer (restates_clause_id)
        2. Normalized section identifier
        3. Topic + slot keys overlap / clause_uid
        4. Text similarity (>0.60 token ratio)
      - Detects text modifications with unified diff snippets
      - Identifies changed structured numeric slots (payment days, late fees, SLA uptime, caps)
      - Surfaces clauses present in A but omitted in B, and new provisions in B
    """
    ag_a = db.query(Agreement).filter(Agreement.id == agreement_a_id, Agreement.tenant_id == tenant_id).first()
    ag_b = db.query(Agreement).filter(Agreement.id == agreement_b_id, Agreement.tenant_id == tenant_id).first()

    if not ag_a or not ag_b:
        return {
            "status": "not_found",
            "message": f"Agreement #{agreement_a_id} or #{agreement_b_id} not found for tenant '{tenant_id}'."
        }

    clauses_a = db.query(Clause).filter(Clause.agreement_id == agreement_a_id, Clause.tenant_id == tenant_id).all()
    clauses_b = db.query(Clause).filter(Clause.agreement_id == agreement_b_id, Clause.tenant_id == tenant_id).all()

    matched_pairs: list[tuple[Clause, Clause, str]] = []
    unmatched_a: list[Clause] = list(clauses_a)
    unmatched_b: list[Clause] = list(clauses_b)

    # 1. Alignment Priority: Explicit restatement pointer
    for ca in list(unmatched_a):
        for cb in list(unmatched_b):
            is_restate = (
                getattr(cb, "restates_clause_id", None) == ca.id or
                getattr(ca, "restates_clause_id", None) == cb.id
            )
            if is_restate:
                matched_pairs.append((ca, cb, f"restate:{ca.section or ca.topic}"))
                unmatched_a.remove(ca)
                unmatched_b.remove(cb)
                break

    # 2. Alignment Priority: Normalized section
    for ca in list(unmatched_a):
        if ca.section:
            sec_norm = normalize_section(ca.section)
            if sec_norm:
                for cb in list(unmatched_b):
                    if cb.section and normalize_section(cb.section) == sec_norm:
                        matched_pairs.append((ca, cb, ca.section))
                        unmatched_a.remove(ca)
                        unmatched_b.remove(cb)
                        break

    # 3. Alignment Priority: Stable clause_uid or Topic + Slot keys overlap
    for ca in list(unmatched_a):
        if getattr(ca, "clause_uid", None):
            for cb in list(unmatched_b):
                if getattr(cb, "clause_uid", None) == ca.clause_uid:
                    matched_pairs.append((ca, cb, ca.topic))
                    unmatched_a.remove(ca)
                    unmatched_b.remove(cb)
                    break

    for ca in list(unmatched_a):
        if ca.topic and ca.topic != "GENERAL_COMMERCIAL":
            slots_a_keys = set((ca.structured_slots or {}).keys())
            for cb in list(unmatched_b):
                if cb.topic == ca.topic:
                    slots_b_keys = set((cb.structured_slots or {}).keys())
                    # Prefer if structured slots share keys or both have matching topic
                    if slots_a_keys and slots_b_keys and (slots_a_keys & slots_b_keys):
                        matched_pairs.append((ca, cb, ca.topic))
                        unmatched_a.remove(ca)
                        unmatched_b.remove(cb)
                        break
                    elif not slots_a_keys and not slots_b_keys:
                        matched_pairs.append((ca, cb, ca.topic))
                        unmatched_a.remove(ca)
                        unmatched_b.remove(cb)
                        break

    # 4. Alignment Priority: Text similarity (>= 0.60)
    for ca in list(unmatched_a):
        best_cb = None
        best_ratio = 0.0
        for cb in unmatched_b:
            ratio = difflib.SequenceMatcher(None, ca.content.lower(), cb.content.lower()).ratio()
            if ratio >= 0.60 and ratio > best_ratio:
                best_ratio = ratio
                best_cb = cb
        if best_cb:
            matched_pairs.append((ca, best_cb, ca.section or ca.topic))
            unmatched_a.remove(ca)
            unmatched_b.remove(best_cb)

    modified_provisions = []
    slot_changes = []

    for ca, cb, key in matched_pairs:
        slots_a = ca.structured_slots or {}
        slots_b = cb.structured_slots or {}
        differing_slots = {}
        for sk in set(slots_a.keys()) | set(slots_b.keys()):
            va = slots_a.get(sk)
            vb = slots_b.get(sk)
            val_a = get_slot_val(va)
            val_b = get_slot_val(vb)
            if val_a != val_b:
                differing_slots[sk] = {"instrument_a": val_a, "instrument_b": val_b}
                slot_changes.append({
                    "key": key,
                    "slot": sk,
                    "value_a": val_a,
                    "value_b": val_b,
                    "section_a": ca.section,
                    "section_b": cb.section
                })

        if ca.content.strip() != cb.content.strip():
            diff_lines = list(difflib.unified_diff(
                ca.content.splitlines(),
                cb.content.splitlines(),
                fromfile=f"{ag_a.title} ({ca.section})",
                tofile=f"{ag_b.title} ({cb.section})",
                lineterm=""
            ))
            modified_provisions.append({
                "key": key,
                "section_a": ca.section,
                "section_b": cb.section,
                "diff": "\n".join(diff_lines),
                "slot_changes": differing_slots
            })

    omitted_in_b = [{
        "section": c.section,
        "title": c.title,
        "topic": c.topic,
        "content_snippet": c.content[:150]
    } for c in unmatched_a]

    new_in_b = [{
        "section": c.section,
        "title": c.title,
        "topic": c.topic,
        "content_snippet": c.content[:150]
    } for c in unmatched_b]

    return {
        "status": "compared",
        "agreement_a": {"id": ag_a.id, "title": ag_a.title, "instrument_type": ag_a.instrument_type},
        "agreement_b": {"id": ag_b.id, "title": ag_b.title, "instrument_type": ag_b.instrument_type},
        "summary": {
            "total_clauses_a": len(clauses_a),
            "total_clauses_b": len(clauses_b),
            "matched_count": len(matched_pairs),
            "modified_count": len(modified_provisions),
            "omitted_in_b_count": len(omitted_in_b),
            "new_in_b_count": len(new_in_b),
            "slot_changes_count": len(slot_changes)
        },
        "slot_changes_count": len(slot_changes),
        "slot_changes": slot_changes,
        "modified_provisions": modified_provisions,
        "omitted_in_b": omitted_in_b,
        "new_in_b": new_in_b
    }
