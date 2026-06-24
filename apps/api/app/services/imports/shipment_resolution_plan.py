"""Job-scoped shipment evidence steward resolution plan (transient, regenerate anytime).

Uses scoring from ``shipment_evidence_resolution_plan`` plus historical customer hints.
Does not persist plans to the database.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_customer_intelligence import (
    HistoricalCustomerResolution,
    lookup_historical_customer_resolution,
)
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CANDIDATE_TERMINAL_STATUSES,
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
    build_shipment_enrich_refs,
    score_shipment_customer_token_candidate,
    score_shipment_distributor_candidate,
)

PlanStatus = Literal["ready", "needs_review", "needs_defaults"]
SuggestedAction = Literal[
    "map_distributor",
    "create_provisional_distributor",
    "map_customer",
    "create_provisional_customer",
    "none",
]

_ACTION_MAP = {
    "map_distributor": "map_distributor",
    "create_provisional_distributor": "create_provisional_distributor",
    "map_customer": "map_customer",
    "create_provisional_customer": "create_provisional_customer",
    "needs_review": "none",
}


def _terminal_candidate(cand: ImportEntityMappingCandidate) -> bool:
    return (cand.status or "").strip() in SHIPMENT_CANDIDATE_TERMINAL_STATUSES


def _plan_common(cand: ImportEntityMappingCandidate) -> dict[str, Any]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    return {
        "candidate_id": int(cand.id),
        "entity_type": cand.entity_type,
        "normalized_key": cand.normalized_key,
        "row_count": int(cand.row_count or 0),
        "status": cand.status,
        "party": ctx.get("party"),
        "resolution_blockers": [],
        "hold_for_manual_review": False,
    }


def _first_sample(cand: ImportEntityMappingCandidate) -> str:
    samples = cand.sample_raw_values if isinstance(cand.sample_raw_values, list) else []
    for item in samples:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return (cand.normalized_key or "").strip()


def _special_category_blocks(ctx: dict[str, Any]) -> str | None:
    sc = ctx.get("special_category")
    if isinstance(sc, str) and sc.strip() in ("noise_only", "internal_note"):
        return sc.strip()
    return None


def _score_to_plan_row(
    cand: ImportEntityMappingCandidate,
    score: dict[str, Any],
    *,
    historical: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _plan_common(cand)
    raw_action = str(score.get("suggested_action") or "")
    target_id = score.get("suggested_entity_id")
    confidence = float(score.get("confidence_score") or 0.0)
    reason = str(score.get("match_reason") or "")

    if historical is not None:
        return {
            **base,
            "suggested_action": "map_customer",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": float(historical.get("confidence") or confidence),
            "reason": historical.get("reason") or "Previously resolved — confirm before applying",
            "suggested_target_id": historical.get("customer_id"),
            "needs_defaults": False,
            "historical_resolution": historical,
            "resolution_blockers": ["previously_resolved_confirm"],
        }

    if raw_action == "needs_review":
        blockers = [reason or "ambiguous_match"]
        return {
            **base,
            "suggested_action": "none",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": confidence,
            "reason": reason or "Needs steward review",
            "suggested_target_id": target_id,
            "needs_defaults": False,
            "resolution_blockers": blockers,
        }

    mapped_action = _ACTION_MAP.get(raw_action, "none")
    ready = mapped_action != "none"
    plan_status: PlanStatus = "ready" if ready else "needs_review"
    human_reason = {
        "map_distributor": "Matched existing distributor (alias or dimension)",
        "map_customer": "Matched existing channel partner (alias or dimension)",
        "create_provisional_distributor": "No distributor match — propose provisional + alias",
        "create_provisional_customer": "No channel partner match — propose provisional + alias",
    }.get(mapped_action, reason or "No automatic action")

    return {
        **base,
        "suggested_action": mapped_action,
        "plan_status": plan_status,
        "ready": ready,
        "confidence": confidence,
        "reason": human_reason,
        "suggested_target_id": int(target_id) if target_id is not None and ready else target_id,
        "needs_defaults": False,
        "resolution_blockers": [] if ready else [reason or "not_ready"],
    }


def _load_historical_shipment_customer_resolutions(
    session: Session,
    *,
    source_definition_id: int | None,
    current_job_id: int,
) -> dict[tuple[int | None, str], HistoricalCustomerResolution]:
    """Prior resolved ``shipment_customer_token`` candidates on other jobs (same source)."""
    out: dict[tuple[int | None, str], HistoricalCustomerResolution] = {}
    if source_definition_id is None:
        return out
    dom_col = ImportEntityMappingCandidate.context["dominant_unresolved_distributor_id"].astext
    rows = session.execute(
        select(
            ImportEntityMappingCandidate.normalized_key,
            ImportEntityMappingCandidate.suggested_entity_id,
            ImportEntityMappingCandidate.match_reason,
            ImportEntityMappingCandidate.import_job_id,
            ImportJob.completed_at,
            dom_col,
        )
        .join(ImportJob, ImportJob.id == ImportEntityMappingCandidate.import_job_id)
        .where(
            ImportEntityMappingCandidate.entity_type == SHIPMENT_CUSTOMER_ENTITY,
            ImportEntityMappingCandidate.source_definition_id == int(source_definition_id),
            ImportEntityMappingCandidate.import_job_id != int(current_job_id),
            ImportEntityMappingCandidate.status == "resolved",
            ImportEntityMappingCandidate.suggested_entity_id.isnot(None),
        )
        .order_by(ImportJob.completed_at.desc().nullslast(), ImportEntityMappingCandidate.id.desc())
        .limit(5000)
    ).all()
    for nk, cid, reason, jid, _completed, dom_raw in rows:
        key = nk if isinstance(nk, str) else str(nk or "")
        if not key or cid is None:
            continue
        dist_key: int | None = None
        if dom_raw is not None and str(dom_raw).strip().isdigit():
            dist_key = int(str(dom_raw).strip())
        nk_norm = _norm_key(key)
        if not nk_norm:
            continue
        slot_scoped = (dist_key, nk_norm)
        slot_global = (None, nk_norm)
        if slot_scoped not in out:
            out[slot_scoped] = HistoricalCustomerResolution(
                customer_id=int(cid),
                import_job_id=int(jid),
                match_reason=str(reason or "")[:256] or None,
                confidence=0.85,
                resolution_kind="shipment_steward_map",
            )
        if slot_global not in out:
            out[slot_global] = out[slot_scoped]
    return out


def plan_shipment_candidate_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    job: ImportJob,
    *,
    refs,
    historical_index: dict | None,
) -> dict[str, Any]:
    if _terminal_candidate(cand):
        base = _plan_common(cand)
        return {
            **base,
            "suggested_action": "none",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": 0.0,
            "reason": "Candidate already terminal — no auto action",
            "suggested_target_id": None,
            "needs_defaults": False,
            "resolution_blockers": ["terminal_status"],
        }

    ctx = cand.context if isinstance(cand.context, dict) else {}
    if blocked := _special_category_blocks(ctx):
        base = _plan_common(cand)
        return {
            **base,
            "suggested_action": "none",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": 0.0,
            "reason": f"Special category {blocked} — manual steward only",
            "suggested_target_id": None,
            "needs_defaults": False,
            "resolution_blockers": [f"special_category:{blocked}"],
        }

    source_def_id = job.source.id if job.source else cand.source_definition_id

    if cand.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY:
        score = score_shipment_distributor_candidate(session, cand, source_definition_id=source_def_id, refs=refs)
        return _score_to_plan_row(cand, score)

    if cand.entity_type == SHIPMENT_CUSTOMER_ENTITY:
        score = score_shipment_customer_token_candidate(
            session, cand, source_definition_id=source_def_id, refs=refs
        )
        if historical_index is not None:
            dist_id = None
            dom = ctx.get("dominant_unresolved_distributor_id")
            if dom is not None:
                try:
                    dist_id = int(dom)
                except (TypeError, ValueError):
                    dist_id = None
            hist = lookup_historical_customer_resolution(
                historical_index,
                distributor_id=dist_id,
                normalized_key=cand.normalized_key or "",
                customer_raw=_first_sample(cand),
                dealer_group_raw=cand.dealer_group_token,
            )
            if hist is not None:
                hist_cid = int(hist.customer_id)
                score_cid = score.get("suggested_entity_id")
                score_action = str(score.get("suggested_action") or "")

                if score_action == "map_customer" and score_cid is not None and int(score_cid) == hist_cid:
                    boosted = dict(score)
                    boosted["confidence_score"] = max(float(score.get("confidence_score") or 0), 1.0)
                    mr = str(boosted.get("match_reason") or "")
                    if "corroborated" not in mr:
                        boosted["match_reason"] = (
                            f"{mr}_corroborated_prior_shipment" if mr else "corroborated_prior_shipment"
                        )
                    return _score_to_plan_row(cand, boosted)

                if score_action == "map_customer" and score_cid is not None and int(score_cid) != hist_cid:
                    historical = {
                        "label": "previously_resolved",
                        "import_job_id": hist.import_job_id,
                        "customer_id": hist.customer_id,
                        "match_reason": hist.match_reason,
                        "resolution_kind": hist.resolution_kind,
                        "confidence": float(hist.confidence),
                        "reason": (
                            f"Previously resolved on import job {hist.import_job_id} "
                            f"({hist.resolution_kind}) conflicts with current match — review required"
                        ),
                    }
                    return _score_to_plan_row(cand, score, historical=historical)

                return _score_to_plan_row(
                    cand,
                    {
                        "suggested_action": "map_customer",
                        "suggested_entity_id": hist_cid,
                        "match_reason": "prior_shipment_steward_resolution",
                        "confidence_score": 0.95,
                    },
                )

        return _score_to_plan_row(cand, score)

    base = _plan_common(cand)
    return {
        **base,
        "suggested_action": "none",
        "plan_status": "needs_review",
        "ready": False,
        "confidence": 0.0,
        "reason": "Unsupported entity type",
        "suggested_target_id": None,
        "needs_defaults": False,
        "resolution_blockers": ["unsupported_entity_type"],
    }


def _enrich_target_labels(session: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dist_ids = {
        int(r["suggested_target_id"])
        for r in rows
        if r.get("suggested_target_id") is not None and r.get("entity_type") == SHIPMENT_DISTRIBUTOR_ENTITY
    }
    cust_ids = {
        int(r["suggested_target_id"])
        for r in rows
        if r.get("suggested_target_id") is not None and r.get("entity_type") == SHIPMENT_CUSTOMER_ENTITY
    }
    dist_labels: dict[int, str] = {}
    cust_labels: dict[int, str] = {}
    if dist_ids:
        for d in session.scalars(select(DimDistributor).where(DimDistributor.id.in_(dist_ids))).all():
            dist_labels[int(d.id)] = (d.name or d.code or "")[:256]
    if cust_ids:
        for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(cust_ids))).all():
            cust_labels[int(c.id)] = (c.name or c.code or "")[:256]
    out = []
    for r in rows:
        row = dict(r)
        tid = row.get("suggested_target_id")
        if tid is not None:
            et = row.get("entity_type")
            if et == SHIPMENT_DISTRIBUTOR_ENTITY:
                row["suggested_target_label"] = dist_labels.get(int(tid))
            elif et == SHIPMENT_CUSTOMER_ENTITY:
                row["suggested_target_label"] = cust_labels.get(int(tid))
        out.append(row)
    return out


def build_shipment_resolution_plan_sync(
    session: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None,
) -> dict[str, Any]:
    job = session.get(ImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    if (job.template_slug or "") != "inbound_shipments":
        raise ValueError("Job is not a shipment evidence import")

    q = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    plan_truncated = False
    if candidate_ids:
        q = q.where(ImportEntityMappingCandidate.id.in_(candidate_ids))
    else:
        q = q.limit(100)
        plan_truncated = True

    cands = list(
        session.scalars(
            q.order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.id)
        ).all()
    )
    refs = build_shipment_enrich_refs(session) if cands else None
    source_def_id = job.source.id if job.source else None
    historical_index = _load_historical_shipment_customer_resolutions(
        session, source_definition_id=source_def_id, current_job_id=job_id
    )

    rows = []
    for c in cands:
        if _terminal_candidate(c):
            continue
        rows.append(plan_shipment_candidate_sync(session, c, job, refs=refs, historical_index=historical_index))

    ready_n = sum(1 for r in rows if r.get("ready"))
    out: dict[str, Any] = {
        "import_job_id": job_id,
        "rows": _enrich_target_labels(session, rows),
        "summary": {
            "total": len(rows),
            "ready": ready_n,
            "not_ready": len(rows) - ready_n,
            "hold": 0,
        },
    }
    if plan_truncated:
        out["plan_scope_note"] = (
            "candidate_ids omitted — only the first 100 candidates were planned. "
            "Pass candidate_ids (e.g. current table page) for scoped planning."
        )
    return out


def merge_shipment_resolution_plan_row_for_apply(
    *,
    cand: ImportEntityMappingCandidate,
    base: dict[str, Any],
    ov: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    hold = bool(ov and ov.get("hold_for_manual_review"))
    if hold:
        return {
            "hold_for_manual_review": True,
            "ready": False,
            "suggested_action": "none",
            "suggested_target_id": None,
            "resolution_blockers": ["hold_for_manual_review"],
        }

    action = str((ov or {}).get("suggested_action") or base.get("suggested_action") or "none")
    target = (ov or {}).get("suggested_target_id", base.get("suggested_target_id"))
    confirm_hist = bool((ov or {}).get("confirm_previously_resolved"))
    ready = bool(base.get("ready"))

    hist = base.get("historical_resolution")
    if isinstance(hist, dict) and hist.get("label") == "previously_resolved":
        if not confirm_hist:
            ready = False
            blockers.append("previously_resolved_confirm")
        else:
            ready = True
            action = "map_customer"
            target = base.get("suggested_target_id")

    if ov and ov.get("suggested_action"):
        action = str(ov["suggested_action"])
        target = ov.get("suggested_target_id", target)
        if action in ("map_distributor", "map_customer", "create_provisional_distributor", "create_provisional_customer"):
            ready = True

    if action in ("map_distributor", "map_customer") and target is None:
        ready = False
        blockers.append("missing_target_id")

    if not ready and not blockers:
        blockers.extend(list(base.get("resolution_blockers") or []))

    return {
        "hold_for_manual_review": False,
        "ready": ready and not blockers,
        "suggested_action": action,
        "suggested_target_id": target,
        "resolution_blockers": blockers,
        "confirm_previously_resolved": confirm_hist,
    }


def _attach_effective_fields(base: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    row = dict(base)
    row["ready"] = merged.get("ready")
    row["hold_for_manual_review"] = merged.get("hold_for_manual_review")
    row["suggested_action"] = merged.get("suggested_action")
    row["suggested_target_id"] = merged.get("suggested_target_id")
    row["resolution_blockers"] = merged.get("resolution_blockers")
    row["effective_action"] = merged.get("suggested_action")
    row["effective_target_id"] = merged.get("suggested_target_id")
    row["effective_ready"] = merged.get("ready")
    return row


def build_shipment_resolution_plan_effective_sync(
    session: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None,
    overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    by_cid: dict[int, dict[str, Any]] = {}
    for o in overrides:
        cid = int(o["candidate_id"])
        rest = {k: v for k, v in o.items() if k != "candidate_id"}
        by_cid[cid] = {**by_cid.get(cid, {}), **rest}

    baseline = build_shipment_resolution_plan_sync(session, job_id, candidate_ids=candidate_ids)
    rows: list[dict[str, Any]] = []
    for base in baseline.get("rows") or []:
        cid = int(base["candidate_id"])
        cand = session.get(ImportEntityMappingCandidate, cid)
        if cand is None:
            continue
        merged = merge_shipment_resolution_plan_row_for_apply(cand=cand, base=base, ov=by_cid.get(cid))
        rows.append(_attach_effective_fields(base, merged))

    ready_n = sum(1 for r in rows if r.get("ready"))
    hold_n = sum(1 for r in rows if r.get("hold_for_manual_review"))
    return {
        "import_job_id": job_id,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ready": ready_n,
            "not_ready": len(rows) - ready_n,
            "hold": hold_n,
        },
    }
