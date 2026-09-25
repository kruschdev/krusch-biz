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

from sqlalchemy import func, or_
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
    """
    Check if two counterparty strings identify the exact same entity.
    Requires exact match of normalized entity names (zero fuzzy substring containment).
    """
    if not party_a or not party_b:
        return False
    norm_a = normalize_party_name(party_a)
    norm_b = normalize_party_name(party_b)
    if not norm_a or not norm_b:
        return False
    return norm_a == norm_b


def is_clause_temporally_valid(clause: Clause, as_of: date) -> bool:
    """
    Check if a specific clause is temporally valid as of a UTC date.
    Evaluates clause.is_active, clause.effective_from, clause.effective_to,
    and any temporal bounds in clause.structured_slots.
    """
    if not getattr(clause, "is_active", True):
        return False
    cl_eff_from = getattr(clause, "effective_from", None)
    if cl_eff_from and to_utc_date(cl_eff_from) > as_of:
        return False
    cl_eff_to = getattr(clause, "effective_to", None)
    if cl_eff_to and to_utc_date(cl_eff_to) <= as_of:
        return False
    if clause.structured_slots and isinstance(clause.structured_slots, dict):
        slot_from = clause.structured_slots.get("effective_from") or clause.structured_slots.get("effective_date")
        if slot_from:
            try:
                if to_utc_date(slot_from) > as_of:
                    return False
            except Exception:
                pass
        slot_to = clause.structured_slots.get("effective_to") or clause.structured_slots.get("expiration_date")
        if slot_to:
            try:
                if to_utc_date(slot_to) <= as_of:
                    return False
            except Exception:
                pass
    return True


def is_sow_instrument(ag: Agreement, valid_relations: list[AgreementRelation] | None = None) -> bool:
    """
    Classify whether an agreement is a Statement of Work / Schedule vs Master Agreement.
    Strictly excludes amendments and addenda.
    """
    itype = (ag.instrument_type or "").strip().lower()
    title = (ag.title or "").strip().upper()
    if itype in ("amendment", "amendment_addendum", "rider", "addendum"):
        return False
    if "AMENDMENT" in title or "ADDENDUM" in title:
        return False
    if itype in ("statement_of_work", "sow", "schedule"):
        return True
    if valid_relations:
        for r in valid_relations:
            if r.source_agreement_id == ag.id and r.relation_type in ("SCHEDULE_OF", "STATEMENT_OF_WORK"):
                return True
    if re.search(r"\b(sow|statement\s+of\s+work|fee\s+schedule|pricing\s+schedule)\b", title, re.IGNORECASE):
        return True
    return False


def get_playbook(
    db: Session,
    tenant_id: str,
    deal_id: int | None = None,
    counterparty: str | None = None,
    playbook_name: str | None = None
) -> Any | None:
    """Resolve deal playbook by deal_id, counterparty, name, or tenant default."""
    from .db import DealPlaybook
    if playbook_name:
        pb = db.query(DealPlaybook).filter(DealPlaybook.tenant_id == tenant_id, DealPlaybook.playbook_name == playbook_name).first()
        if pb:
            return pb
    if deal_id:
        pb = db.query(DealPlaybook).filter(DealPlaybook.tenant_id == tenant_id, DealPlaybook.playbook_name == f"deal_{deal_id}").first()
        if pb:
            return pb
    if counterparty:
        pb = db.query(DealPlaybook).filter(DealPlaybook.tenant_id == tenant_id, DealPlaybook.playbook_name == counterparty).first()
        if pb:
            return pb
    pb = db.query(DealPlaybook).filter(DealPlaybook.tenant_id == tenant_id, DealPlaybook.playbook_name == "default_commercial").first()
    if pb:
        return pb
    return db.query(DealPlaybook).filter(DealPlaybook.tenant_id == tenant_id).first()


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


def parse_relation_scope(scope_obj: Any) -> dict[str, list[str]]:
    """
    Parse a relation scope into a first-class typed dictionary:
      {
        "topics": list[str],
        "sections": list[str],
        "slot_keys": list[str]
      }
    """
    res: dict[str, list[str]] = {"topics": [], "sections": [], "slot_keys": []}
    if scope_obj is None:
        return res

    if hasattr(scope_obj, "scope_type"):
        s_type = (getattr(scope_obj, "scope_type", None) or "ALL").upper()
        if s_type == "TOPICS":
            res["topics"] = [t.upper() for t in (getattr(scope_obj, "scope_topics", []) or [])]
        elif s_type == "SECTIONS":
            res["sections"] = [normalize_section(s) for s in (getattr(scope_obj, "scope_sections", []) or []) if normalize_section(s)]
        raw_scope = getattr(scope_obj, "clause_scope", None)
    elif isinstance(scope_obj, dict):
        res["topics"] = [t.upper() for t in scope_obj.get("topics", [])]
        res["sections"] = [normalize_section(s) for s in scope_obj.get("sections", []) if normalize_section(s)]
        res["slot_keys"] = list(scope_obj.get("slot_keys", []))
        return res
    elif isinstance(scope_obj, str):
        raw_scope = scope_obj
    else:
        raw_scope = None

    if not raw_scope or raw_scope.strip().upper() in ("ALL", "*"):
        return res

    scope_str = raw_scope.strip()
    if scope_str.startswith("{") and scope_str.endswith("}"):
        try:
            parsed_json = json.loads(scope_str)
            if isinstance(parsed_json, dict):
                if "topics" in parsed_json:
                    res["topics"] = [t.upper() for t in parsed_json["topics"]]
                if "sections" in parsed_json:
                    res["sections"] = [normalize_section(s) for s in parsed_json["sections"] if normalize_section(s)]
                if "slot_keys" in parsed_json:
                    res["slot_keys"] = list(parsed_json["slot_keys"])
                return res
        except Exception:
            pass

    if scope_str.lower().startswith(("slots:", "slot:")):
        slots_part = scope_str.split(":", 1)[1]
        res["slot_keys"] = [k.strip() for k in slots_part.split(",") if k.strip()]
        return res

    if scope_str.lower().startswith("topic:"):
        res["topics"] = [scope_str.split(":", 1)[1].strip().upper()]
        return res

    if scope_str.upper() in TOPIC_ALIASES or scope_str.upper() in SOW_CONTROLLING_TOPICS or scope_str.upper() in MSA_CONTROLLING_TOPICS:
        res["topics"] = [scope_str.upper()]
        return res

    norm_s = normalize_section(scope_str)
    if norm_s:
        res["sections"] = [norm_s]
    return res


def is_scope_match(scope_obj: Any, clause: Clause, topic: str) -> bool:
    """
    Verify if a relation's first-class typed scope governs a specific clause or topic.
    Scope = {topics[], sections[], slot_keys[]}.
    """
    if scope_obj is None:
        return True

    scope_dict = parse_relation_scope(scope_obj)
    topics = scope_dict["topics"]
    sections = scope_dict["sections"]
    slot_keys = scope_dict["slot_keys"]

    if not topics and not sections and not slot_keys:
        return True

    if topics:
        if topic.upper() not in topics and not any(t in TOPIC_ALIASES.get(topic.upper(), []) for t in topics):
            return False

    if sections:
        c_sec = normalize_section(clause.section)
        c_title = (clause.title or "").strip().lower()
        sec_match = (c_sec in sections) or any(s in c_title for s in sections)
        if not sec_match:
            return False

    if slot_keys:
        cl_slots = clause.structured_slots or {}
        if not any(k in cl_slots for k in slot_keys):
            return False

    return True


def get_party_agreements(db: Session, tenant_id: str, counterparty: str) -> list[Agreement]:
    """
    Fetch agreements for a strictly matched counterparty entity or alias.
    Resolves canonical Party entity and PartyAlias records if present.
    STRICT SECURITY INVARIANT: Zero fallback to all tenant agreements.
    Uses Party / PartyAlias as the ONLY join key, with exact normalized equality.
    Zero substring ILIKE prefiltering (prevents over-fetching and tenant leaks).
    """
    from .db import Party, PartyAlias

    target_clean = counterparty.strip()
    norm_target = normalize_party_name(target_clean)

    # 1. Authoritative resolution through Party / PartyAlias join key
    party = db.query(Party).filter(
        Party.tenant_id == tenant_id,
        or_(
            func.lower(Party.canonical_name) == target_clean.lower(),
            func.lower(Party.canonical_name) == norm_target.lower()
        )
    ).first()

    if not party:
        alias = db.query(PartyAlias).filter(
            PartyAlias.tenant_id == tenant_id,
            or_(
                func.lower(PartyAlias.alias_name) == target_clean.lower(),
                func.lower(PartyAlias.alias_name) == norm_target.lower()
            )
        ).first()
        if alias:
            party = alias.party

    if party:
        valid_names = {party.canonical_name.strip().lower(), normalize_party_name(party.canonical_name)}
        for a in party.aliases:
            valid_names.add(a.alias_name.strip().lower())
            valid_names.add(normalize_party_name(a.alias_name))

        agreements = db.query(Agreement).filter(
            Agreement.tenant_id == tenant_id,
            or_(
                Agreement.party_id == party.id,
                func.lower(Agreement.counterparty).in_([n for n in valid_names if n])
            )
        ).all()
        return agreements

    # 2. Strict fail-closed fallback when no Party entity exists in store:
    # Exact normalized equality only — no substring ilike prefilter!
    tenant_agreements = db.query(Agreement).filter(Agreement.tenant_id == tenant_id).all()
    matched = [ag for ag in tenant_agreements if is_party_match(ag.counterparty, counterparty)]
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

    # First, detect cycles among SUPERSEDES relations using DFS
    adj: dict[int, list[int]] = {}
    for r in valid_relations:
        if r.relation_type == "SUPERSEDES":
            adj.setdefault(r.source_agreement_id, []).append(r.target_agreement_id)

    visited_dfs: set[int] = set()
    rec_stack: set[int] = set()

    def dfs_cycle(u: int) -> bool:
        visited_dfs.add(u)
        rec_stack.add(u)
        for v in adj.get(u, []):
            if v == u:  # self loop
                return True
            if v in rec_stack:
                return True
            if v not in visited_dfs:
                if dfs_cycle(v):
                    return True
        rec_stack.remove(u)
        return False

    for node in list(adj.keys()):
        if node not in visited_dfs:
            if dfs_cycle(node):
                cycle_detected = True
                break

    # Transitive traversal to find fully/scoped superseded agreements
    queue = list(active_ag_ids)
    depth = 0

    while queue and depth < depth_cap:
        depth += 1
        current_source = queue.pop(0)

        for edge in supersedes_by_source.get(current_source, []):
            target = edge.target_agreement_id
            if target == current_source:
                cycle_detected = True
                continue

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


def detect_amends_cycle(valid_relations: list[AgreementRelation]) -> bool:
    """
    Detect directed cycles or self-loops in AMENDS relations using DFS.
    """
    adj: dict[int, list[int]] = {}
    for r in valid_relations:
        if r.relation_type == "AMENDS":
            if r.source_agreement_id == r.target_agreement_id:
                return True
            adj.setdefault(r.source_agreement_id, []).append(r.target_agreement_id)

    visited_dfs: set[int] = set()
    rec_stack: set[int] = set()

    def dfs(u: int) -> bool:
        visited_dfs.add(u)
        rec_stack.add(u)
        for v in adj.get(u, []):
            if v == u:
                return True
            if v in rec_stack:
                return True
            if v not in visited_dfs:
                if dfs(v):
                    return True
        rec_stack.remove(u)
        return False

    for node in list(adj.keys()):
        if node not in visited_dfs:
            if dfs(node):
                return True
    return False


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
        result_dict["trace_persisted"] = True
    except Exception as exc:
        logger.warning(f"Could not persist ResolutionTraceRecord: {exc}")
        result_dict["trace_persisted"] = False


def compute_resolution_confidence(
    trail: list[dict[str, Any]],
    has_competing_peers: bool = False,
    missing_dates: bool = False,
    is_keyword_fallback: bool = False,
    cycle_detected: bool = False,
    base_confidence: float = 0.85
) -> tuple[float, list[dict[str, Any]]]:
    """
    Compute dynamic, non-hardcoded resolution quality and itemized deductions.
    Returns (resolution_quality, deductions).
    Cycle or competing peers yields exactly 0.0 (never clamped to 0.1).
    """
    deductions: list[dict[str, Any]] = []

    if cycle_detected:
        deductions.append({
            "code": "GRAPH_CYCLE",
            "penalty": 1.0,
            "reason": "Circular precedence dependency detected in relation DAG"
        })
        return 0.0, deductions

    if has_competing_peers:
        deductions.append({
            "code": "COMPETING_PEERS",
            "penalty": 1.0,
            "reason": "Multiple competing peer instruments without reconciling edge"
        })
        return 0.0, deductions

    conf = 1.0 if trail else base_confidence

    if missing_dates:
        deductions.append({
            "code": "MISSING_DATES",
            "penalty": 0.15,
            "reason": "Agreement missing execution or effective date"
        })
        conf -= 0.15
    if is_keyword_fallback:
        deductions.append({
            "code": "KEYWORD_FALLBACK",
            "penalty": 0.20,
            "reason": "Resolved via keyword matching rather than canonical topic tag"
        })
        conf -= 0.20

    score = max(0.0, min(1.0, round(conf, 2)))
    return score, deductions


def resolve_controlling_clause(
    db: Session,
    tenant_id: str,
    counterparty: str,
    topic: str,
    as_of_date: Any = None,
    deal_id: int | None = None,
    playbook_name: str | None = None,
    persist_trace: bool = True
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
        res_quality = result_dict.get("resolution_quality", result_dict.get("confidence", 0.0))
        result_dict["resolution_quality"] = res_quality
        result_dict["confidence"] = res_quality
        result_dict.setdefault("resolution_deductions", [])
        if persist_trace:
            _persist_trace_record(db, tenant_id, counterparty, topic, as_of, result_dict)
        else:
            result_dict["trace_persisted"] = False
            trace_id = str(uuid.uuid4())
            winner = result_dict.get("controlling_clause")
            winner_ag_id = winner.get("agreement_id") if isinstance(winner, dict) else None
            winner_cl_id = winner.get("id") if isinstance(winner, dict) else None
            result_dict["resolution_trace"] = {
                "trace_id": trace_id,
                "as_of_date": str(as_of),
                "counterparty": counterparty,
                "topic": topic,
                "status": result_dict.get("status"),
                "controlling_clause_id": winner_cl_id,
                "controlling_agreement_id": winner_ag_id,
                "confidence": res_quality,
                "resolution_quality": res_quality,
                "resolution_deductions": result_dict.get("resolution_deductions", []),
                "resolution_rationale": result_dict.get("resolution_rationale"),
                "amendment_trail": result_dict.get("amendment_trail", []),
                "proposed_relations_advisory": proposed_relations_advisory,
                "conflicting_candidates": result_dict.get("conflicting_candidates", []),
                "trace_persisted": False,
            }
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
        rel_status = getattr(rel, "status", None) or "proposed"
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
        if rel_status not in ("confirmed", "accepted"):
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

    # 5. Fetch candidate clauses matching topic (strictly from surviving agreements)
    is_keyword_fallback = False
    topic_candidates = TOPIC_ALIASES.get(topic, [topic])
    raw_candidates = db.query(Clause).filter(
        Clause.tenant_id == tenant_id,
        Clause.agreement_id.in_(surviving_ag_ids),
        Clause.is_active.is_(True),
        Clause.topic.in_(topic_candidates)
    ).all()
    candidate_clauses = [c for c in raw_candidates if is_clause_temporally_valid(c, as_of)]

    # Check confirmed INCORPORATES relations: union incorporated provisions into candidate authorities
    incorporates_relations = [
        r for r in valid_relations
        if r.relation_type == "INCORPORATES"
        and (getattr(r, "status", None) or "proposed") in ("confirmed", "accepted")
        and r.source_agreement_id in surviving_ag_ids
    ]
    incorporated_clauses: list[dict[str, Any]] = []
    for inc_rel in incorporates_relations:
        inc_raw = db.query(Clause).filter(
            Clause.tenant_id == tenant_id,
            Clause.agreement_id == inc_rel.target_agreement_id,
            Clause.is_active.is_(True),
            Clause.topic.in_(topic_candidates)
        ).all()
        for ic in inc_raw:
            if is_clause_temporally_valid(ic, as_of):
                candidate_clauses.append(ic)
                incorporated_clauses.append({
                    "id": ic.id,
                    "agreement_id": ic.agreement_id,
                    "agreement_title": ag_by_id[ic.agreement_id].title if ic.agreement_id in ag_by_id else "Incorporated Instrument",
                    "section": ic.section,
                    "title": ic.title,
                    "topic": ic.topic,
                    "structured_slots": ic.structured_slots,
                    "content": ic.content
                })

    if not candidate_clauses:
        return _finalize_result({
            "status": "topic_not_found",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"No clauses found addressing topic '{topic}' across agreements for '{counterparty}'.",
            "confidence": 0.0
        })

    # Index relations by target agreement for fast AMENDS lookup
    # Apply draft isolation on AMENDS: draft agreements cannot amend executed agreements
    amends_by_target: dict[int, list[AgreementRelation]] = {}
    for rel in valid_relations:
        if rel.relation_type == "AMENDS":
            src_ag = ag_by_id.get(rel.source_agreement_id)
            tgt_ag = ag_by_id.get(rel.target_agreement_id)
            if src_ag and tgt_ag:
                if getattr(src_ag, "execution_status", "executed") == "draft" and getattr(tgt_ag, "execution_status", "executed") != "draft":
                    logger.info(f"Draft isolation: draft {src_ag.id} cannot amend executed {tgt_ag.id}")
                    continue
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
    amends_cycle_detected = detect_amends_cycle(valid_relations)

    def _rel_eff_date(r: AgreementRelation) -> date:
        if r.effective_date:
            return to_utc_date(r.effective_date)
        src_ag = ag_by_id.get(r.source_agreement_id)
        if src_ag and src_ag.effective_date:
            return to_utc_date(src_ag.effective_date)
        return date.min

    for base_clause in candidate_clauses:
        if base_clause.agreement_id in fully_superseded_ag_ids:
            continue
        if base_clause.id in amended_clause_ids:
            continue

        # Check scoped supersession
        is_scoped_out = False
        for sup_ag_id, sup_scope in scoped_superseded:
            if base_clause.agreement_id == sup_ag_id and is_scope_match(sup_scope, base_clause, topic):
                is_scoped_out = True
                break
        if is_scoped_out:
            continue

        # Check clause temporal validity
        if not is_clause_temporally_valid(base_clause, as_of):
            continue

        # Walk AMENDS edges forward from this base clause
        trail: list[dict[str, Any]] = []
        current_clause = base_clause
        effective_slots = dict(base_clause.structured_slots or {})
        visited_clauses = {current_clause.id}
        applied_ag_ids = {base_clause.agreement_id}
        depth = 0

        while depth < 32:
            depth += 1

            # Sibling & chained amendment evaluation:
            # Gather all candidate amendments targeting ANY agreement currently in applied_ag_ids
            candidate_amends: list[tuple[AgreementRelation, Clause]] = []
            for rel in valid_relations:
                if rel.relation_type != "AMENDS":
                    continue
                if rel.target_agreement_id not in applied_ag_ids:
                    continue
                if rel.source_agreement_id in applied_ag_ids:
                    continue
                if rel.source_agreement_id not in active_ag_ids or rel.source_agreement_id in fully_superseded_ag_ids:
                    continue

                # Check scoped supersession on source
                is_src_scoped_out = False
                for sup_ag_id, sup_scope in scoped_superseded:
                    if rel.source_agreement_id == sup_ag_id and is_scope_match(sup_scope, current_clause, topic):
                        is_src_scoped_out = True
                        break
                if is_src_scoped_out:
                    continue

                # Invariant: Draft agreement cannot amend executed agreement
                src_ag = ag_by_id.get(rel.source_agreement_id)
                tgt_ag = ag_by_id.get(rel.target_agreement_id)
                if src_ag and tgt_ag:
                    if getattr(src_ag, "execution_status", "executed") == "draft" and getattr(tgt_ag, "execution_status", "executed") != "draft":
                        logger.info(f"Skipping AMENDS edge: draft {src_ag.id} cannot amend executed {tgt_ag.id}")
                        continue

                if not is_scope_match(rel.clause_scope, current_clause, topic):
                    continue

                if _rel_eff_date(rel) > as_of:
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
                    if not is_clause_temporally_valid(sc, as_of):
                        continue
                    if sc.topic == topic or is_scope_match(rel.clause_scope, sc, topic):
                        matching_amending_clause = sc
                        break

                if matching_amending_clause:
                    candidate_amends.append((rel, matching_amending_clause))

            if not candidate_amends:
                break

            # Order chronologically ascending by effective date to step forward temporally
            candidate_amends.sort(key=lambda pair: _rel_eff_date(pair[0]))

            chosen_rel, matching_sc = candidate_amends[0]

            if matching_sc.id in visited_clauses or chosen_rel.source_agreement_id in applied_ag_ids:
                amends_cycle_detected = True
                break

            visited_clauses.add(matching_sc.id)
            amended_clause_ids.add(current_clause.id)
            amended_clause_ids.add(base_clause.id)
            applied_ag_ids.add(chosen_rel.source_agreement_id)

            # Slot inheritance: overlay amended slots onto inherited base slots
            # First-class typed scope: if slot_keys are specified, overlay ONLY those keys!
            rel_scope = parse_relation_scope(chosen_rel)
            target_slot_keys = rel_scope.get("slot_keys", [])
            if target_slot_keys:
                amd_slots = {k: v for k, v in (matching_sc.structured_slots or {}).items() if k in target_slot_keys}
            else:
                amd_slots = dict(matching_sc.structured_slots or {})

            overridden_keys = [k for k in amd_slots.keys() if k in effective_slots]
            inherited_keys = [k for k in effective_slots.keys() if k not in amd_slots]
            effective_slots.update(amd_slots)

            target_title = ag_by_id[chosen_rel.target_agreement_id].title if chosen_rel.target_agreement_id in ag_by_id else "Agreement"
            source_title = ag_by_id[matching_sc.agreement_id].title if matching_sc.agreement_id in ag_by_id else "Agreement"

            trail.append({
                "relation": "AMENDS",
                "scope": chosen_rel.clause_scope or "ALL",
                "from_agreement_id": chosen_rel.target_agreement_id,
                "from_agreement_title": target_title,
                "from_section": current_clause.section,
                "to_agreement_id": matching_sc.agreement_id,
                "to_agreement_title": source_title,
                "to_section": matching_sc.section,
                "effective_date": str(chosen_rel.effective_date) if chosen_rel.effective_date else None,
                "inherited_slots": inherited_keys,
                "overridden_slots": overridden_keys,
            })

            current_clause = matching_sc

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

    # 7. Evaluate CARVES_OUT Relations (Narrowing Qualifications)
    # CARVES_OUT attaches exceptions to winner; never a second controller
    subordinate_relations = [r for r in valid_relations if r.relation_type == "CARVES_OUT"]
    if len(unique_terminals) > 1 and subordinate_relations:
        # Check if one candidate is a CARVES_OUT exception instrument of the other
        pruned_terminals: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
        for cl, tr, sl in unique_terminals:
            is_subordinate_source = False
            for sr in subordinate_relations:
                if sr.source_agreement_id == cl.agreement_id:
                    # cl is from the carve-out instrument
                    is_subordinate_source = True
                    # Find the target terminal candidate to attach carve-out qualification
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

    # INCORPORATES: Union incorporated provisions into candidate authority set; never a second controller
    incorporates_rels = [r for r in valid_relations if r.relation_type == "INCORPORATES"]
    if len(unique_terminals) > 1 and incorporates_rels:
        pruned_inc_terminals: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
        for cl, tr, sl in unique_terminals:
            is_inc_source = False
            for ir in incorporates_rels:
                target_ag = ag_by_id.get(ir.target_agreement_id)

                inc_ag_id = None
                gov_ag_id = None
                if ir.source_agreement_id == cl.agreement_id:
                    inc_ag_id = ir.source_agreement_id
                    gov_ag_id = ir.target_agreement_id
                elif ir.target_agreement_id == cl.agreement_id:
                    if target_ag and (
                        (target_ag.instrument_type or "").lower() in ("exhibit", "schedule", "addendum")
                        or "exhibit" in (target_ag.title or "").lower()
                        or "schedule" in (target_ag.title or "").lower()
                    ):
                        inc_ag_id = ir.target_agreement_id
                        gov_ag_id = ir.source_agreement_id

                if inc_ag_id == cl.agreement_id and gov_ag_id:
                    for target_cl, target_tr, target_sl in unique_terminals:
                        if target_cl.agreement_id == gov_ag_id:
                            is_inc_source = True
                            incorporated_clauses.append({
                                "id": cl.id,
                                "agreement_id": cl.agreement_id,
                                "agreement_title": ag_by_id[cl.agreement_id].title if cl.agreement_id in ag_by_id else "Incorporated Instrument",
                                "section": cl.section,
                                "title": cl.title,
                                "topic": cl.topic,
                                "structured_slots": cl.structured_slots,
                                "content": cl.content
                            })
                            target_tr.append({
                                "relation": "INCORPORATES",
                                "scope": ir.clause_scope or "ALL",
                                "from_agreement_id": cl.agreement_id,
                                "from_agreement_title": ag_by_id[cl.agreement_id].title if cl.agreement_id in ag_by_id else "Incorporated Instrument",
                                "from_section": cl.section,
                                "to_agreement_id": target_cl.agreement_id,
                                "to_agreement_title": ag_by_id[target_cl.agreement_id].title if target_cl.agreement_id in ag_by_id else "Governing Agreement",
                                "to_section": target_cl.section,
                                "effective_date": str(ir.effective_date) if ir.effective_date else None,
                            })
                            break
                    if is_inc_source:
                        break
            if not is_inc_source:
                pruned_inc_terminals.append((cl, tr, sl))

        if pruned_inc_terminals:
            unique_terminals = pruned_inc_terminals

    # 7b. Fail-Closed on Cycle Detection (Priority 3: Cycle is a data error, not a haircut)
    has_cycle = supersedes_cycle or amends_cycle_detected
    if has_cycle:
        cycle_type = "SUPERSEDES" if supersedes_cycle else "AMENDS"
        if persist_trace:
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

        confidence, deductions = compute_resolution_confidence(
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
            "incorporated_clauses": incorporated_clauses,
            "resolution_rationale": rationale,
            "confidence": confidence,
            "resolution_quality": confidence,
            "resolution_deductions": deductions
        })

    # 9. Multiple Surviving Candidates: Order of Precedence (SOW vs MSA via DealPlaybook)
    playbook = get_playbook(db, tenant_id, deal_id=deal_id, counterparty=counterparty, playbook_name=playbook_name)
    sow_topics = set(playbook.sow_controlling_topics) if (playbook and playbook.sow_controlling_topics) else SOW_CONTROLLING_TOPICS
    msa_topics = set(playbook.master_controlling_topics) if (playbook and playbook.master_controlling_topics) else MSA_CONTROLLING_TOPICS

    sow_candidates: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []
    msa_candidates: list[tuple[Clause, list[dict[str, Any]], dict[str, Any]]] = []

    for item in unique_terminals:
        cl = item[0]
        ag = ag_by_id.get(cl.agreement_id)
        if ag and is_sow_instrument(ag, valid_relations):
            sow_candidates.append(item)
        else:
            msa_candidates.append(item)

    if len(sow_candidates) == 1 and len(msa_candidates) == 1 and len(unique_terminals) == 2:
        sow_candidate, sow_trail, sow_slots = sow_candidates[0]
        msa_candidate, msa_trail, msa_slots = msa_candidates[0]

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
            confidence, deductions = compute_resolution_confidence(
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
                "incorporated_clauses": incorporated_clauses,
                "resolution_rationale": (
                    f"Resolved via order of precedence: Statement of Work '{ag_winner.title if ag_winner else 'SOW'}' "
                    f"controls for scoped topic '{topic}' over Master Services Agreement."
                ),
                "confidence": confidence,
                "resolution_quality": confidence,
                "resolution_deductions": deductions
            })
        elif topic in msa_topics or topic not in sow_topics:
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
            confidence, deductions = compute_resolution_confidence(
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
                "incorporated_clauses": incorporated_clauses,
                "resolution_rationale": (
                    f"Resolved via order of precedence: Master Services Agreement '{ag_winner.title if ag_winner else 'MSA'}' "
                    f"controls for general legal governance ('{topic}') over Statement of Work."
                ),
                "confidence": confidence,
                "resolution_quality": confidence,
                "resolution_deductions": deductions
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
    if persist_trace:
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
    as_of_date: Any = None,
    deal_id: int | None = None
) -> list[dict[str, Any]]:
    """
    Scan for unresolved commercial conflicts across a counterparty's agreement portfolio.
    Runs POST-RESOLUTION:
      1. Resolves all topics present in active agreements using resolve_controlling_clause.
      2. If a topic returns 'ambiguous', flags as an active conflict (AMBIGUOUS_CONTROLLING_INSTRUMENT).
      3. For surviving operative clauses across different agreements, identifies differing slot values
         where no precedence edge reconciles them (DIVERGENT_OPERATIVE_TERMS).
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
        # Pass persist_trace=False so conflict detection does not pollute audit logs or commit transactions
        res = resolve_controlling_clause(db, tenant_id, counterparty, top, as_of, deal_id=deal_id, persist_trace=False)
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
        elif res.get("status") == "resolved":
            # Compare structured slot values across active candidate clauses
            topic_candidates = TOPIC_ALIASES.get(top, [top])
            active_clauses = db.query(Clause).filter(
                Clause.tenant_id == tenant_id,
                Clause.agreement_id.in_(ag_ids),
                Clause.is_active.is_(True),
                Clause.topic.in_(topic_candidates)
            ).all()
            active_clauses = [c for c in active_clauses if is_clause_temporally_valid(c, as_of)]

            for i in range(len(active_clauses)):
                for j in range(i + 1, len(active_clauses)):
                    c1, c2 = active_clauses[i], active_clauses[j]
                    if c1.agreement_id == c2.agreement_id:
                        continue
                    slots1 = c1.structured_slots or {}
                    slots2 = c2.structured_slots or {}
                    differing = {}
                    for sk in set(slots1.keys()) & set(slots2.keys()):
                        v1 = get_slot_val(slots1[sk])
                        v2 = get_slot_val(slots2[sk])
                        if v1 is not None and v2 is not None and v1 != v2:
                            differing[sk] = {"clause_1": v1, "clause_2": v2}
                    if differing:
                        resolved_trail = res.get("amendment_trail", [])
                        trail_ag_ids = {h.get("from_agreement_id") for h in resolved_trail} | {h.get("to_agreement_id") for h in resolved_trail}
                        on_trail = (c1.agreement_id in trail_ag_ids and c2.agreement_id in trail_ag_ids)
                        unscoped_differing = dict(differing)
                        if on_trail:
                            reconciled_keys = set()
                            for h in resolved_trail:
                                rel_from = h.get("from_agreement_id")
                                rel_to = h.get("to_agreement_id")
                                if (rel_from in (c1.agreement_id, c2.agreement_id)) or (rel_to in (c1.agreement_id, c2.agreement_id)):
                                    raw_scope = h.get("scope")
                                    parsed = parse_relation_scope(raw_scope)
                                    if parsed["slot_keys"]:
                                        reconciled_keys.update(parsed["slot_keys"])
                                    else:
                                        # If scope has no specific slot keys restricted, covers all slots for that topic
                                        reconciled_keys.update(differing.keys())
                            unscoped_differing = {k: v for k, v in differing.items() if k not in reconciled_keys}

                        if unscoped_differing:
                            ag1_title = next((a.title for a in agreements if a.id == c1.agreement_id), "Agreement 1")
                            ag2_title = next((a.title for a in agreements if a.id == c2.agreement_id), "Agreement 2")
                            conflicts.append({
                                "topic": top,
                                "conflict_type": "DIVERGENT_OPERATIVE_TERMS",
                                "severity": "MEDIUM",
                                "explanation": (
                                    f"Topic '{top}' has divergent operative terms between '{ag1_title}' ({c1.section}) "
                                    f"and '{ag2_title}' ({c2.section}) with unscoped differing slots: {unscoped_differing}."
                                ),
                                "differing_slots": unscoped_differing,
                                "candidates": [
                                    {"clause_id": c1.id, "agreement_id": c1.agreement_id, "agreement_title": ag1_title, "slots": slots1},
                                    {"clause_id": c2.id, "agreement_id": c2.agreement_id, "agreement_title": ag2_title, "slots": slots2},
                                ]
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
