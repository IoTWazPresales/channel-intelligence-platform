"""Resolution hints for ``ImportEntityMappingCandidate`` rows with ``entity_type == shipment_distributor``.

Scores are **UI hints only**; steward apply paths remain strict (alias + explicit distributor choice).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.import_distributor_si import DistributorSourceTokenAlias, ImportEntityMappingCandidate
from app.services.imports.distributor_sales_inventory import _norm_key
from app.utils.json_safe import to_jsonable


SHIPMENT_DISTRIBUTOR_ENTITY = "shipment_distributor"


def _alias_distributor_ids(db: Session, *, source_definition_id: int | None, normalized_token: str) -> list[int]:
    if not normalized_token:
        return []
    q = select(DistributorSourceTokenAlias.distributor_id).where(
        DistributorSourceTokenAlias.normalized_token == normalized_token,
        DistributorSourceTokenAlias.status == "approved",
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                DistributorSourceTokenAlias.source_definition_id.is_(None),
                DistributorSourceTokenAlias.source_definition_id == source_definition_id,
            )
        )
    else:
        q = q.where(DistributorSourceTokenAlias.source_definition_id.is_(None))
    rows = list(dict.fromkeys(db.scalars(q).all()))
    return [int(x) for x in rows]


def _exact_dim_matches(db: Session, *, normalized_token: str) -> list[int]:
    """Exact dim_distributor match on normalized code or full normalized name (strict)."""
    nk = (normalized_token or "").strip().lower()
    if not nk:
        return []
    out: list[int] = []
    for d in db.scalars(select(DimDistributor)).all():
        code = (d.code or "").strip().lower()
        name = (d.name or "").strip().lower()
        if code == nk or name == nk:
            out.append(int(d.id))
    return sorted(set(out))


def score_shipment_distributor_candidate(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    source_definition_id: int | None,
) -> dict[str, Any]:
    """Return plan fields: suggested_action, suggested_entity_id, match_reason, confidence_score."""
    nt = (cand.normalized_key or "").strip()
    alias_ids = _alias_distributor_ids(db, source_definition_id=source_definition_id, normalized_token=nt)
    dim_ids = _exact_dim_matches(db, normalized_token=nt)

    if len(alias_ids) == 1:
        return {
            "suggested_action": "map_distributor",
            "suggested_entity_id": int(alias_ids[0]),
            "match_reason": "approved_distributor_source_token_alias",
            "confidence_score": 1.0,
        }
    if len(alias_ids) > 1:
        return {
            "suggested_action": "needs_review",
            "suggested_entity_id": None,
            "match_reason": "multiple_approved_distributor_aliases_for_token",
            "confidence_score": 0.4,
        }

    if len(dim_ids) == 1:
        return {
            "suggested_action": "map_distributor",
            "suggested_entity_id": int(dim_ids[0]),
            "match_reason": "exact_dim_distributor_code_or_name",
            "confidence_score": 0.95,
        }
    if len(dim_ids) > 1:
        return {
            "suggested_action": "needs_review",
            "suggested_entity_id": None,
            "match_reason": "multiple_dim_distributors_exact_match_token",
            "confidence_score": 0.35,
        }

    return {
        "suggested_action": "create_provisional_distributor",
        "suggested_entity_id": None,
        "match_reason": "no_alias_or_exact_dim_match",
        "confidence_score": 0.2,
    }


def enrich_shipment_distributor_candidates(db: Session, *, import_job_id: int, source_definition_id: int | None) -> None:
    """Persist planner hints onto ``shipment_distributor`` candidates for one import job."""
    rows = list(
        db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(import_job_id),
                ImportEntityMappingCandidate.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY,
            )
        ).all()
    )
    for cand in rows:
        if cand.status in ("resolved", "ignored", "waived_open_channel"):
            continue
        plan = score_shipment_distributor_candidate(db, cand, source_definition_id=source_definition_id)
        cand.suggested_entity_id = plan.get("suggested_entity_id")
        cand.match_reason = str(plan.get("match_reason") or "")[:256] or None
        cand.confidence_score = plan.get("confidence_score")
        ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
        ctx["suggested_action"] = plan["suggested_action"]
        cand.context = to_jsonable(ctx)
        db.add(cand)
