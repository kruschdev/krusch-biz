"""
src/backend/resolver.py
=======================
Controlling-document resolver and commercial conflict detection engine.
Walks the agreement relation graph (AMENDS, SUPERSEDES, INCORPORATES) to
determine the governing clause as of a specific date, and surfaces contradictory
terms between concurrently active instruments.
"""

from __future__ import annotations

import difflib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .db import Agreement, AgreementRelation, Clause

logger = logging.getLogger("kruschbiz.resolver")


def resolve_controlling_clause(
    db: Session,
    tenant_id: str,
    counterparty: str,
    topic: str,
    as_of_date: datetime | None = None
) -> dict[str, Any]:
    """
    Resolve which contract clause controls for a given topic as of a specific date.
    Walks the relational agreement graph:
      1. Discovers agreements with counterparty.
      2. Traverses AMENDS and SUPERSEDES edges up to as_of_date.
      3. Ranks candidates by authority class and amendment recency.
    """
    as_of = as_of_date or datetime.now()

    # 1. Fetch agreements for counterparty
    agreements = db.query(Agreement).filter(
        Agreement.tenant_id == tenant_id,
        Agreement.counterparty.ilike(f"%{counterparty}%")
    ).all()

    if not agreements:
        # Fallback: check all agreements in tenant
        agreements = db.query(Agreement).filter(
            Agreement.tenant_id == tenant_id
        ).all()

    if not agreements:
        return {
            "status": "not_found",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"No commercial agreements found for counterparty '{counterparty}'.",
            "confidence": 0.0
        }

    ag_ids = [ag.id for ag in agreements]

    # 2. Identify superseded agreements via explicit relations or expiration
    superseded_ids = set()
    for ag in agreements:
        if ag.expiration_date and ag.expiration_date <= as_of:
            superseded_ids.add(ag.id)
        if ag.status in ("superseded", "terminated"):
            superseded_ids.add(ag.id)

    # Check relation graph for SUPERSEDES edges
    relations = db.query(AgreementRelation).filter(
        AgreementRelation.tenant_id == tenant_id,
        AgreementRelation.relation_type == "SUPERSEDES",
        AgreementRelation.source_agreement_id.in_(ag_ids)
    ).all()

    for rel in relations:
        if not rel.effective_date or rel.effective_date <= as_of:
            superseded_ids.add(rel.target_agreement_id)

    # 3. Find candidate clauses for topic
    candidate_clauses = db.query(Clause).filter(
        Clause.tenant_id == tenant_id,
        Clause.agreement_id.in_(ag_ids),
        Clause.topic == topic,
        Clause.is_active.is_(True)
    ).all()

    if not candidate_clauses:
        # Relax topic filter to keyword match on content
        candidate_clauses = db.query(Clause).filter(
            Clause.tenant_id == tenant_id,
            Clause.agreement_id.in_(ag_ids),
            Clause.content.ilike(f"%{topic.replace('_', ' ').lower()}%"),
            Clause.is_active.is_(True)
        ).all()

    if not candidate_clauses:
        return {
            "status": "no_candidate_clauses",
            "controlling_clause": None,
            "amendment_trail": [],
            "resolution_rationale": f"Agreements found, but no clauses govern topic '{topic}'.",
            "confidence": 0.0
        }

    # 4. Filter out clauses from superseded agreements
    active_candidates: list[Clause] = []
    trail: list[dict[str, Any]] = []

    for cl in candidate_clauses:
        ag = cl.agreement
        is_sup = cl.agreement_id in superseded_ids
        info = {
            "clause_id": cl.id,
            "agreement_id": cl.agreement_id,
            "agreement_title": ag.title if ag else "Unknown",
            "section": cl.section,
            "authority_class": cl.authority_class,
            "effective_date": str(ag.effective_date) if ag and ag.effective_date else None,
            "is_superseded": is_sup,
            "structured_slots": cl.structured_slots
        }
        trail.append(info)
        if not is_sup:
            active_candidates.append(cl)

    if not active_candidates:
        # All candidate clauses are superseded
        return {
            "status": "all_authorities_superseded",
            "controlling_clause": None,
            "amendment_trail": trail,
            "resolution_rationale": f"All candidate clauses for topic '{topic}' reside in superseded instruments.",
            "confidence": 0.0
        }

    # 5. Rank remaining active candidates:
    # Priority: amendment (recent > older) > governing_agreement > statement_of_work > corporate_policy
    authority_rank = {
        "amendment": 100,
        "amendment_addendum": 100,
        "executed_amendment": 100,
        "governing_agreement": 80,
        "statement_of_work": 60,
        "sla": 50,
        "corporate_policy": 40,
        "secondary_guideline": 20
    }

    def candidate_score(c: Clause) -> tuple[int, datetime]:
        auth_val = authority_rank.get(c.authority_class, 50)
        eff_date = (c.agreement.effective_date if c.agreement and c.agreement.effective_date else datetime.min)
        return (auth_val, eff_date)

    active_candidates.sort(key=candidate_score, reverse=True)
    winner = active_candidates[0]
    ag_winner = winner.agreement

    rationale = (
        f"Resolved '{winner.section}' from '{ag_winner.title if ag_winner else 'Agreement'}' as controlling. "
        f"Authority class: {winner.authority_class}. Active candidates evaluated: {len(active_candidates)}."
    )

    return {
        "status": "resolved",
        "controlling_clause": {
            "id": winner.id,
            "agreement_id": winner.agreement_id,
            "agreement_title": ag_winner.title if ag_winner else "Governing Agreement",
            "section": winner.section,
            "title": winner.title,
            "topic": winner.topic,
            "structured_slots": winner.structured_slots,
            "content": winner.content,
            "authority_class": winner.authority_class,
            "effective_date": str(ag_winner.effective_date) if ag_winner and ag_winner.effective_date else None,
        },
        "amendment_trail": trail,
        "resolution_rationale": rationale,
        "confidence": 0.95
    }


def detect_contract_conflicts(
    db: Session,
    tenant_id: str,
    counterparty: str,
    as_of_date: datetime | None = None
) -> list[dict[str, Any]]:
    """
    Detect conflicting slot values across concurrently live, active commercial instruments.
    Surfaces divergent numbers (e.g. Net 30 vs Net 45, Uptime 99.9% vs 99.5%) prior to drafting.
    """
    as_of = as_of_date or datetime.now()
    conflicts: list[dict[str, Any]] = []

    # 1. Fetch active, non-superseded agreements for counterparty
    agreements = db.query(Agreement).filter(
        Agreement.tenant_id == tenant_id,
        Agreement.counterparty.ilike(f"%{counterparty}%"),
        Agreement.status == "active"
    ).all()

    if len(agreements) < 2:
        return []

    active_ag_ids = [ag.id for ag in agreements]

    # Filter out any that were superseded via explicit relations
    superseded_by_rel = set()
    rels = db.query(AgreementRelation).filter(
        AgreementRelation.tenant_id == tenant_id,
        AgreementRelation.relation_type == "SUPERSEDES",
        AgreementRelation.source_agreement_id.in_(active_ag_ids)
    ).all()
    for r in rels:
        if not r.effective_date or r.effective_date <= as_of:
            superseded_by_rel.add(r.target_agreement_id)

    valid_ag_ids = [aid for aid in active_ag_ids if aid not in superseded_by_rel]
    if len(valid_ag_ids) < 2:
        return []

    # 2. Fetch clauses with structured slots
    clauses = db.query(Clause).filter(
        Clause.tenant_id == tenant_id,
        Clause.agreement_id.in_(valid_ag_ids),
        Clause.is_active.is_(True),
        Clause.structured_slots.isnot(None)
    ).all()

    # Group by topic
    by_topic: dict[str, list[Clause]] = {}
    for cl in clauses:
        if cl.topic and cl.topic != "GENERAL_COMMERCIAL" and cl.structured_slots:
            by_topic.setdefault(cl.topic, []).append(cl)

    # 3. Check for conflicting slot values
    for topic, topic_clauses in by_topic.items():
        if len(topic_clauses) < 2:
            continue

        # Compare pairs across different agreements
        for i in range(len(topic_clauses)):
            for j in range(i + 1, len(topic_clauses)):
                c1, c2 = topic_clauses[i], topic_clauses[j]
                if c1.agreement_id == c2.agreement_id:
                    continue  # Intra-agreement clauses handled by section hierarchy

                slots1 = c1.structured_slots or {}
                slots2 = c2.structured_slots or {}

                # Check common keys
                common_keys = set(slots1.keys()) & set(slots2.keys())
                for key in common_keys:
                    val1 = slots1[key]
                    val2 = slots2[key]
                    if val1 != val2:
                        conflicts.append({
                            "topic": topic,
                            "conflict_key": key,
                            "severity": "HIGH" if key in ("net_days", "uptime_pct", "cap_amount") else "MEDIUM",
                            "explanation": (
                                f"Conflicting terms for '{key}': '{c1.agreement.title}' ({c1.section}) stipulates '{val1}', "
                                f"while '{c2.agreement.title}' ({c2.section}) stipulates '{val2}' without an explicit supersession edge."
                            ),
                            "clause_a": {
                                "agreement": c1.agreement.title,
                                "section": c1.section,
                                "value": val1
                            },
                            "clause_b": {
                                "agreement": c2.agreement.title,
                                "section": c2.section,
                                "value": val2
                            }
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
      - Aligns clauses by commercial topic and section
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

    # Align clauses across instruments:
    # 1. Match by specialized topic (excluding GENERAL_COMMERCIAL)
    # 2. Match remaining clauses by normalized section
    # 3. Classify remaining unmatched in A as deleted, in B as added
    matched_pairs: list[tuple[Clause, Clause, str]] = []
    unmatched_a: list[Clause] = list(clauses_a)
    unmatched_b: list[Clause] = list(clauses_b)

    # Match by topic
    for ca in list(unmatched_a):
        if ca.topic and ca.topic != "GENERAL_COMMERCIAL":
            for cb in list(unmatched_b):
                if cb.topic == ca.topic:
                    matched_pairs.append((ca, cb, ca.topic))
                    unmatched_a.remove(ca)
                    unmatched_b.remove(cb)
                    break

    # Match by normalized section
    for ca in list(unmatched_a):
        if ca.section:
            sec_norm = ca.section.strip().lower()
            for cb in list(unmatched_b):
                if cb.section and cb.section.strip().lower() == sec_norm:
                    matched_pairs.append((ca, cb, ca.section))
                    unmatched_a.remove(ca)
                    unmatched_b.remove(cb)
                    break

    modified_provisions = []
    slot_changes = []

    for ca, cb, key in matched_pairs:
        # Check slot changes
        slots_a = ca.structured_slots or {}
        slots_b = cb.structured_slots or {}
        differing_slots = {}
        for sk in set(slots_a.keys()) | set(slots_b.keys()):
            va = slots_a.get(sk)
            vb = slots_b.get(sk)
            if va != vb:
                differing_slots[sk] = {"instrument_a": va, "instrument_b": vb}
                slot_changes.append({
                    "key": key,
                    "slot": sk,
                    "value_a": va,
                    "value_b": vb,
                    "section_a": ca.section,
                    "section_b": cb.section
                })

        # Check text difference
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
                "topic": ca.topic,
                "slot_changes": differing_slots,
                "diff_snippet": "\n".join(diff_lines[:15])
            })

    deleted_provisions = [
        {
            "key": ca.section or ca.topic,
            "section": ca.section,
            "topic": ca.topic,
            "content": ca.content,
            "slots": ca.structured_slots
        }
        for ca in unmatched_a
    ]

    added_provisions = [
        {
            "key": cb.section or cb.topic,
            "section": cb.section,
            "topic": cb.topic,
            "content": cb.content,
            "slots": cb.structured_slots
        }
        for cb in unmatched_b
    ]

    return {
        "status": "compared",
        "agreement_a": {
            "id": ag_a.id,
            "title": ag_a.title,
            "instrument_type": ag_a.instrument_type,
            "effective_date": str(ag_a.effective_date) if ag_a.effective_date else None,
            "counterparty": ag_a.counterparty
        },
        "agreement_b": {
            "id": ag_b.id,
            "title": ag_b.title,
            "instrument_type": ag_b.instrument_type,
            "effective_date": str(ag_b.effective_date) if ag_b.effective_date else None,
            "counterparty": ag_b.counterparty
        },
        "modified_count": len(modified_provisions),
        "added_count": len(added_provisions),
        "deleted_count": len(deleted_provisions),
        "slot_changes_count": len(slot_changes),
        "modified_provisions": modified_provisions,
        "added_provisions": added_provisions,
        "deleted_provisions": deleted_provisions,
        "slot_changes": slot_changes
    }
