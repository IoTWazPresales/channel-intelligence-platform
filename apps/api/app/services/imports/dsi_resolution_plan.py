"""Job-scoped DSI steward resolution plan: suggest actions per candidate (transient, regenerate anytime).

Reuses the same resolution rules as validation/steward flows via distributor_sales_inventory helpers.
Does not persist plans to the database (no migration).
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
)
from app.services.imports.distributor_sales_inventory import (
    _load_product_resolution_index,
    _norm_key,
    _resolve_customer,
    _resolve_distributor,
    _resolve_product,
    effective_dsi_customer_primary_for_resolution,
)
from app.services.imports.dsi_steward_candidate_ops import (
    DISTRIBUTOR_PROVISIONAL_SUSPICIOUS,
    StewardOpError,
    _first_sample_raw as dsi_first_sample,
    execute_create_provisional_dsi_customer,
    execute_create_provisional_dsi_distributor,
    execute_ignore_dsi_candidate,
    execute_map_dsi_customer,
    execute_map_dsi_distributor,
    execute_resolve_dsi_product,
)

PlanStatus = Literal["ready", "needs_review", "needs_defaults"]
SuggestedAction = Literal[
    "map_distributor",
    "create_provisional_distributor",
    "map_customer",
    "create_provisional_customer",
    "resolve_product",
    "ignore",
    "none",
]


def _terminal_candidate(cand: ImportEntityMappingCandidate) -> bool:
    return cand.status in ("resolved", "ignored", "waived_open_channel")


def _plan_common(cand: ImportEntityMappingCandidate) -> dict[str, Any]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    return {
        "candidate_id": cand.id,
        "entity_type": cand.entity_type,
        "normalized_key": cand.normalized_key,
        "candidate_status": cand.status,
        "row_count": cand.row_count,
        "total_units": float(cand.total_units) if cand.total_units is not None else None,
        "total_reported_value": float(cand.total_reported_value)
        if cand.total_reported_value is not None
        else None,
    }


def plan_dsi_candidate_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    job: ImportJob,
    prod_idx: ProductResolutionIndex,
    *,
    default_region_id: int | None,
    default_channel_id: int | None,
) -> dict[str, Any]:
    """Return one plan row dict for a candidate (sync Session)."""
    base = _plan_common(cand)
    if _terminal_candidate(cand):
        out = {
            **base,
            "suggested_action": "none",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": 0.0,
            "reason": "Candidate already terminal — no auto action",
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
        }
        return out

    source_def_id = job.source.id if job.source else None

    # --- distributor_token ---
    if cand.entity_type == "distributor_token":
        raw = dsi_first_sample(cand)
        nt = _norm_key(raw or cand.normalized_key or "")
        did, err = _resolve_distributor(session, raw or cand.normalized_key, source_def_id)
        if did is not None:
            return {
                **base,
                "suggested_action": "map_distributor",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.92,
                "reason": "Matched existing distributor (alias or dimension)",
                "suggested_target_id": int(did),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS:
            return {
                **base,
                "suggested_action": "ignore",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.75,
                "reason": "Placeholder-like distributor token — safe to ignore as junk",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        return {
            **base,
            "suggested_action": "create_provisional_distributor",
            "plan_status": "ready",
            "ready": True,
            "confidence": 0.55,
            "reason": "No existing distributor match — propose provisional + alias",
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
        }

    # --- product_identifier ---
    if cand.entity_type == "product_identifier":
        ctx = cand.context if isinstance(cand.context, dict) else {}
        raw = dsi_first_sample(cand)
        pstatus = ctx.get("product_match_status")
        if pstatus == "ambiguous_eligible":
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Multiple eligible Product Master matches — ambiguous; steward must choose product",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if pstatus == "inactive_only" or ctx.get("product_inactive_matches"):
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.25,
                "reason": "Inactive/ineligible matches only — confirm product + audit note in steward UI",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }

        pid, perr, tag, _ev = _resolve_product(raw, prod_idx, None)
        if pid is not None and perr is None:
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.88,
                "reason": f"Single Product Master match ({tag or 'resolved'}) — propose ProductAlias bind",
                "suggested_target_id": int(pid),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        return {
            **base,
            "suggested_action": "resolve_product",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": 0.15,
            "reason": (ctx.get("product_match_summary") or perr or "No safe automatic product match"),
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
        }

    # --- customer_dealer_token ---
    if cand.entity_type == "customer_dealer_token":
        ctx = cand.context if isinstance(cand.context, dict) else {}
        if ctx.get("strategic_channel_hint"):
            return {
                **base,
                "suggested_action": "create_provisional_customer",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Strategic / marketplace-style channel evidence — review before mapping or provisional",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }

        samples = ctx.get("source_customer_name_raw_samples")
        cust_first = samples[0] if isinstance(samples, list) and samples and isinstance(samples[0], str) else None
        dg_raw = ctx.get("dealer_group_account_raw") if isinstance(ctx.get("dealer_group_account_raw"), str) else None
        if not dg_raw and cand.dealer_group_token:
            dg_raw = str(cand.dealer_group_token)

        primary, _notes = effective_dsi_customer_primary_for_resolution(cust_first, dg_raw)
        rcid, diag = _resolve_customer(
            session,
            source_id=source_def_id,
            distributor_id=None,
            customer_raw=primary,
            dealer_group_raw=dg_raw,
            channel_raw=None,
            open_flag_raw=None,
        )
        if rcid is not None:
            return {
                **base,
                "suggested_action": "map_customer",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.9,
                "reason": f"Matched existing customer ({','.join(diag)})",
                "suggested_target_id": int(rcid),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if "ambiguous_customer_name" in diag:
            return {
                **base,
                "suggested_action": "map_customer",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Ambiguous customer name match — pick customer manually",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if "customer_token_placeholder" in diag or "missing_customer_token" in diag:
            return {
                **base,
                "suggested_action": "ignore",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.7,
                "reason": "Blank or placeholder customer evidence — ignore candidate",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }

        prov_ready = bool(default_region_id and default_channel_id)
        return {
            **base,
            "suggested_action": "create_provisional_customer",
            "plan_status": "needs_defaults" if not prov_ready else "ready",
            "ready": prov_ready,
            "confidence": 0.5,
            "reason": "No existing customer match — propose provisional account + source alias",
            "suggested_target_id": None,
            "needs_defaults": not prov_ready,
            "needs_confirm_suspicious_distributor": False,
        }

    return {
        **base,
        "suggested_action": "none",
        "plan_status": "needs_review",
        "ready": False,
        "confidence": 0.0,
        "reason": "Unsupported entity_type for auto plan",
        "suggested_target_id": None,
        "needs_defaults": False,
        "needs_confirm_suspicious_distributor": False,
    }


def build_dsi_resolution_plan_sync(
    session: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None,
    default_region_id: int | None,
    default_channel_id: int | None,
) -> dict[str, Any]:
    job = session.get(ImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    q = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    if candidate_ids:
        q = q.where(ImportEntityMappingCandidate.id.in_(candidate_ids))
    cands = list(session.scalars(q.order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.id)).all())
    prod_idx = _load_product_resolution_index(session)
    rows = [
        plan_dsi_candidate_sync(session, c, job, prod_idx, default_region_id=default_region_id, default_channel_id=default_channel_id)
        for c in cands
    ]
    ready_n = sum(1 for r in rows if r.get("ready"))
    return {
        "import_job_id": job_id,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ready": ready_n,
            "not_ready": len(rows) - ready_n,
        },
        "defaults_used": {
            "region_id": default_region_id,
            "channel_id": default_channel_id,
        },
    }


def snapshot_product_plan_from_context(ctx: dict[str, Any] | None) -> dict[str, Any]:
    """Pure helper for tests: classify product candidate context without DB."""
    if not ctx:
        return {"plan_status": "needs_review", "ready": False}
    ps = ctx.get("product_match_status")
    if ps == "ambiguous_eligible":
        return {"plan_status": "needs_review", "ready": False, "reason": "ambiguous"}
    if ps == "inactive_only" or ctx.get("product_inactive_matches"):
        return {"plan_status": "needs_review", "ready": False, "reason": "inactive_only"}
    return {"plan_status": "unknown", "ready": False}


async def apply_dsi_resolution_plan_rows(
    db: AsyncSession,
    job_id: int,
    candidate_ids: list[int],
    *,
    default_region_id: int | None,
    default_channel_id: int | None,
    partner_tier: str | None,
    provisional_notes_summary: str | None,
    confirm_for_suspicious_distributor_token: bool,
) -> dict[str, Any]:
    """Recompute plan row per id with defaults; execute steward ops when ready (same rules as generate)."""

    def _plan_sync(sess: Session, cid: int, jid: int, dr: int | None, dc: int | None) -> dict[str, Any] | None:
        job = sess.get(ImportJob, jid)
        cand = sess.get(ImportEntityMappingCandidate, cid)
        if not job or not cand or cand.import_job_id != jid:
            return None
        prod_idx = _load_product_resolution_index(sess)
        return plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=dr, default_channel_id=dc)

    results: list[dict[str, Any]] = []
    for cid in candidate_ids:
        row = await db.run_sync(
            lambda s, c=cid, j=job_id, dr=default_region_id, dc=default_channel_id: _plan_sync(s, c, j, dr, dc)
        )
        if row is None:
            results.append({"candidate_id": cid, "ok": False, "detail": "Candidate not found for this job"})
            continue
        if not row.get("ready"):
            results.append({"candidate_id": cid, "ok": False, "detail": "not_ready", "plan": row})
            continue

        cand = await db.get(ImportEntityMappingCandidate, cid)
        if cand is None or cand.import_job_id != job_id:
            results.append({"candidate_id": cid, "ok": False, "detail": "Candidate not found"})
            continue

        action = row.get("suggested_action")
        try:
            if action == "ignore":
                out = await execute_ignore_dsi_candidate(db, cand, notes=None)
            elif action == "map_distributor":
                tid = row.get("suggested_target_id")
                if tid is None:
                    raise StewardOpError("Plan missing distributor target", status_code=400)
                out = await execute_map_dsi_distributor(db, cand, distributor_id=int(tid), raw_token=None)
            elif action == "create_provisional_distributor":
                out = await execute_create_provisional_dsi_distributor(
                    db,
                    cand,
                    display_name_override=None,
                    distributor_code_override=None,
                    confirm_for_suspicious_token=confirm_for_suspicious_distributor_token,
                )
            elif action == "map_customer":
                tid = row.get("suggested_target_id")
                if tid is None:
                    raise StewardOpError("Plan missing customer target", status_code=400)
                out = await execute_map_dsi_customer(db, cand, customer_id=int(tid), raw_token=None)
            elif action == "create_provisional_customer":
                if default_region_id is None or default_channel_id is None:
                    raise StewardOpError("region_id and channel_id required for provisional customer apply", status_code=400)
                out = await execute_create_provisional_dsi_customer(
                    db,
                    cand,
                    display_name_override=None,
                    region_id=int(default_region_id),
                    channel_id=int(default_channel_id),
                    preferred_distributor_id=None,
                    partner_tier=partner_tier,
                    notes_summary=provisional_notes_summary,
                )
            elif action == "resolve_product":
                tid = row.get("suggested_target_id")
                if tid is None:
                    raise StewardOpError("Plan missing product target", status_code=400)
                out = await execute_resolve_dsi_product(
                    db,
                    cand,
                    product_id=int(tid),
                    raw_token=None,
                    confirm_ineligible_product=False,
                    audit_note=None,
                    idempotency_key=None,
                )
            else:
                results.append(
                    {"candidate_id": cid, "ok": False, "detail": f"No executor for action {action}", "plan": row}
                )
                continue
            results.append({"candidate_id": cid, "ok": True, "result": out, "plan": row})
        except StewardOpError as exc:
            results.append({"candidate_id": cid, "ok": False, "detail": exc.detail, "plan": row})

    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "import_job_id": job_id,
        "applied": ok_n,
        "failed": len(results) - ok_n,
        "results": results,
    }

