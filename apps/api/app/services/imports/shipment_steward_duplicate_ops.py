"""Shipment steward duplicate-review ops (customer tokens).

Mirrors DSI acknowledge semantics onto ``shipment_customer_token`` candidates so
``duplicate_unresolved_only`` list filters can clear after a steward decision.
Does not gate the shipment resolution plan (D-004 / shipment plan variance).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.dsi_customer_intelligence import (
    build_duplicate_review_record,
    duplicate_review_decision,
    similarity_score_for_duplicate_peer,
)
from app.services.imports.shipment_evidence_resolution_plan import SHIPMENT_CUSTOMER_ENTITY
from app.services.imports.shipment_evidence_steward_ops import ShipmentStewardOpError
from app.services.imports.shipment_mapping_candidates_list import (
    is_shipment_mapping_candidate_terminal_status,
)


def _shipment_duplicate_review_unresolved(cand: ImportEntityMappingCandidate) -> bool:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    hints = ctx.get("possible_duplicate_of")
    if not isinstance(hints, list) or len(hints) == 0:
        return False
    return duplicate_review_decision(ctx) is None


def _merge_duplicate_review_context(cand: ImportEntityMappingCandidate, review: dict[str, Any]) -> None:
    ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
    ctx["duplicate_review"] = review
    cand.context = ctx


def _peer_keys_from_hints(ctx: dict[str, Any]) -> set[str]:
    hints = ctx.get("possible_duplicate_of")
    out: set[str] = set()
    if not isinstance(hints, list):
        return out
    for h in hints:
        if isinstance(h, str) and h.strip():
            out.add(h.strip())
        elif isinstance(h, dict):
            nk = str(h.get("normalized_key") or "").strip()
            if nk:
                out.add(nk)
    return out


def _get_shipment_customer_peer(
    session: Session, cand: ImportEntityMappingCandidate, peer_normalized_key: str
) -> ImportEntityMappingCandidate | None:
    nk = (peer_normalized_key or "").strip()
    if not nk:
        return None
    return session.scalar(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == cand.import_job_id,
            ImportEntityMappingCandidate.entity_type == SHIPMENT_CUSTOMER_ENTITY,
            ImportEntityMappingCandidate.normalized_key == nk,
        )
    )


def execute_acknowledge_shipment_duplicate_different_entity(
    session: Session,
    cand: ImportEntityMappingCandidate,
    *,
    peer_normalized_key: str,
    audit_note: str | None = None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not shipment_customer_token", status_code=400)
    if is_shipment_mapping_candidate_terminal_status(cand.status):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    if not _shipment_duplicate_review_unresolved(cand):
        raise ShipmentStewardOpError("Duplicate review already recorded for this candidate", status_code=400)

    ctx = cand.context if isinstance(cand.context, dict) else {}
    peer_nk = (peer_normalized_key or "").strip()
    if peer_nk not in _peer_keys_from_hints(ctx):
        raise ShipmentStewardOpError("Peer is not listed in possible_duplicate_of for this candidate", status_code=400)

    peer = _get_shipment_customer_peer(session, cand, peer_nk)
    if peer is None:
        raise ShipmentStewardOpError("Peer candidate not found for this import job", status_code=404)

    score = similarity_score_for_duplicate_peer(ctx, peer_nk)
    review = build_duplicate_review_record(
        decision="different_entity",
        paired_normalized_key=peer.normalized_key,
        similarity_score=score,
        audit_note=audit_note,
        hints_snapshot=ctx.get("possible_duplicate_of") if isinstance(ctx.get("possible_duplicate_of"), list) else [],
    )
    _merge_duplicate_review_context(cand, review)
    cand.status = "acknowledged_unique"
    cand.match_reason = "steward_acknowledged_unique_duplicate"
    session.commit()
    return {
        "ok": True,
        "candidate_id": cand.id,
        "status": "acknowledged_unique",
        "peer_candidate_id": peer.id,
        "duplicate_review": review,
    }


def execute_acknowledge_shipment_duplicate_same_entity(
    session: Session,
    cand: ImportEntityMappingCandidate,
    *,
    peer_normalized_key: str,
    audit_note: str | None = None,
) -> dict[str, Any]:
    """Stamp same-entity duplicate review only — mapping still uses Map / plan apply."""
    if cand.entity_type != SHIPMENT_CUSTOMER_ENTITY:
        raise ShipmentStewardOpError("Not shipment_customer_token", status_code=400)
    if is_shipment_mapping_candidate_terminal_status(cand.status):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    if not _shipment_duplicate_review_unresolved(cand):
        raise ShipmentStewardOpError("Duplicate review already recorded for this candidate", status_code=400)

    ctx = cand.context if isinstance(cand.context, dict) else {}
    peer_nk = (peer_normalized_key or "").strip()
    if peer_nk not in _peer_keys_from_hints(ctx):
        raise ShipmentStewardOpError("Peer is not listed in possible_duplicate_of for this candidate", status_code=400)

    peer = _get_shipment_customer_peer(session, cand, peer_nk)
    if peer is None:
        raise ShipmentStewardOpError("Peer candidate not found for this import job", status_code=404)

    score = similarity_score_for_duplicate_peer(ctx, peer_nk)
    review = build_duplicate_review_record(
        decision="same_entity",
        paired_normalized_key=peer.normalized_key,
        similarity_score=score,
        audit_note=audit_note,
        hints_snapshot=ctx.get("possible_duplicate_of") if isinstance(ctx.get("possible_duplicate_of"), list) else [],
    )
    _merge_duplicate_review_context(cand, review)
    # Keep candidate actionable for Map / plan (unlike different_entity ack).
    session.commit()
    return {
        "ok": True,
        "candidate_id": cand.id,
        "status": cand.status,
        "peer_candidate_id": peer.id,
        "duplicate_review": review,
        "message": "Duplicate marked same entity — map both tokens to the same master customer when ready.",
    }
