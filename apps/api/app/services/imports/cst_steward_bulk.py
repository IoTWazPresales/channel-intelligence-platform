"""CST import steward bulk preview → apply (Unit E S8, shipment-shaped).

Actions:
  - ``ignore`` — mark candidates ignored
  - ``resolve_product`` — map selected tokens to one shared ``product_id`` (entity id);
    valid for both ``cst_product_token`` and ``cst_location_token`` (location uses the
    same body field as the shared engine's resolve_product path)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.cst_mapping_candidates import (
    CST_LOCATION_ENTITY,
    CST_PRODUCT_ENTITY,
    _CST_ENTITY_TYPES,
    _CST_TERMINAL_STATUSES,
    CstCandidateOpError,
    ignore_cst_candidate_sync,
    resolve_cst_candidate_sync,
)

_ALLOWED_ACTIONS = frozenset({"ignore", "resolve_product"})


def _preview_row(
    cand: ImportEntityMappingCandidate,
    *,
    action: str,
    entity_id: int | None,
) -> dict[str, Any]:
    base = {
        "candidate_id": cand.id,
        "entity_type": cand.entity_type,
        "normalized_key": cand.normalized_key,
        "row_count": cand.row_count,
        "status": cand.status,
        "proposed_label": None,
        "alias_evidence": None,
    }
    if cand.status in _CST_TERMINAL_STATUSES:
        return {
            **base,
            "ok": False,
            "skip_reason": "already_terminal",
            "detail": f"Candidate status is {cand.status}",
        }
    if cand.entity_type not in _CST_ENTITY_TYPES:
        return {
            **base,
            "ok": False,
            "skip_reason": "unsupported_entity_type",
            "detail": f"Unsupported entity_type: {cand.entity_type}",
        }
    if action == "ignore":
        return {
            **base,
            "ok": True,
            "skip_reason": None,
            "detail": "Will ignore token",
            "proposed_label": "ignore",
        }
    if action == "resolve_product":
        if entity_id is None or entity_id < 1:
            return {
                **base,
                "ok": False,
                "skip_reason": "missing_target",
                "detail": "product_id / entity target required",
            }
        if cand.entity_type == CST_PRODUCT_ENTITY:
            label = f"product #{entity_id}"
        elif cand.entity_type == CST_LOCATION_ENTITY:
            label = f"location #{entity_id}"
        else:
            label = f"entity #{entity_id}"
        return {
            **base,
            "ok": True,
            "skip_reason": None,
            "detail": f"Will map to {label}",
            "proposed_label": label,
            "proposed_entity_id": entity_id,
        }
    return {
        **base,
        "ok": False,
        "skip_reason": "unsupported_action",
        "detail": f"Unsupported action: {action}",
    }


def preview_cst_steward_bulk(
    session: Session,
    job_id: int,
    *,
    action: str,
    candidate_ids: list[int],
    product_id: int | None = None,
) -> dict[str, Any]:
    if action not in _ALLOWED_ACTIONS:
        raise CstCandidateOpError(400, f"Unsupported CST bulk action: {action}")

    found = {
        c.id: c
        for c in session.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.id.in_(candidate_ids),
            )
        ).all()
    }
    results: list[dict[str, Any]] = []
    for cid in candidate_ids:
        cand = found.get(cid)
        if cand is None:
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "skip_reason": "not_found_or_wrong_job",
                    "detail": "Candidate not found for this job",
                }
            )
            continue
        results.append(_preview_row(cand, action=action, entity_id=product_id))

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "action": action,
        "results": results,
        "totals": {
            "ok_count": ok_count,
            "not_ok_count": len(results) - ok_count,
        },
    }


def apply_cst_steward_bulk(
    session: Session,
    job_id: int,
    *,
    action: str,
    candidate_ids: list[int],
    product_id: int | None = None,
) -> dict[str, Any]:
    preview = preview_cst_steward_bulk(
        session, job_id, action=action, candidate_ids=candidate_ids, product_id=product_id
    )
    results: list[dict[str, Any]] = []
    applied = 0
    failed = 0
    for row in preview["results"]:
        cid = int(row["candidate_id"])
        if not row.get("ok"):
            failed += 1
            results.append({**row, "applied": False})
            continue
        try:
            if action == "ignore":
                ignore_cst_candidate_sync(session, job_id, cid)
            elif action == "resolve_product":
                resolve_cst_candidate_sync(session, job_id, cid, int(product_id or 0))
            else:
                raise CstCandidateOpError(400, f"Unsupported CST bulk action: {action}")
            applied += 1
            results.append({**row, "ok": True, "applied": True})
        except CstCandidateOpError as exc:
            failed += 1
            results.append(
                {
                    "candidate_id": cid,
                    "ok": False,
                    "applied": False,
                    "skip_reason": "apply_failed",
                    "detail": str(exc.detail),
                }
            )
    return {
        "import_job_id": job_id,
        "action": action,
        "applied": applied,
        "failed": failed,
        "results": results,
        "totals": {
            "ok_count": applied,
            "not_ok_count": failed,
        },
    }
