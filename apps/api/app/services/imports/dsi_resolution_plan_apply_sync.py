"""DSI resolution-plan apply — effective plan once, then canonical bulk writers (few commits)."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.session import AsyncSessionLocal
from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import _load_product_resolution_index
from app.services.imports.dsi_bulk_db_commit import commit_session_with_transient_retry
from app.services.imports.dsi_bulk_ignore_sync import run_dsi_bulk_ignore_sync
from app.services.imports.dsi_bulk_map_customers_sync import run_dsi_bulk_map_customers_sync
from app.services.imports.dsi_bulk_map_distributors_sync import run_dsi_bulk_map_distributors_sync
from app.services.imports.dsi_bulk_provisional_customers_sync import run_dsi_bulk_provisional_customers_sync
from app.services.imports.dsi_resolution_plan import (
    apply_dsi_resolution_plan_rows,
    build_dsi_resolution_plan_effective_sync,
)
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

# Legacy export — orchestrator no longer chunks by this size.
APPLY_CHUNK_SIZE = 25


def _persist_dsi_steward_apply_checkpoint(
    job_id: int,
    *,
    processed: int,
    total: int,
    applied: int,
    failed: int,
    interrupted: bool = False,
    error: str | None = None,
) -> None:
    with SessionLocal() as session:
        job = session.get(ImportJob, job_id)
        if job is None:
            return
        meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
        ckpt: dict[str, Any] = {
            "processed": processed,
            "total": total,
            "applied": applied,
            "failed": failed,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if interrupted:
            ckpt["interrupted"] = True
        if error:
            ckpt["error"] = error[:800]
        meta["dsi_steward_apply_checkpoint"] = to_jsonable(ckpt)
        job.staged_metadata = meta
        session.add(job)
        commit_session_with_transient_retry(session)


def _read_dsi_steward_apply_checkpoint(job_id: int) -> dict[str, Any] | None:
    with SessionLocal() as session:
        job = session.get(ImportJob, job_id)
        if job is None or not isinstance(job.staged_metadata, dict):
            return None
        raw = job.staged_metadata.get("dsi_steward_apply_checkpoint")
        return dict(raw) if isinstance(raw, dict) else None


def _finalize_apply_result(
    combined: dict[str, Any],
    *,
    processed: int,
    total: int,
    interrupted: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    """Attach telemetry fields expected by the web poll/apply consumer (F-01)."""
    out = dict(combined)
    out["processed"] = int(processed)
    out["interrupted"] = bool(interrupted)
    out["partial_success"] = bool(interrupted and processed < total)
    if error:
        out["error"] = error[:800]
    return out


def _empty_combined(job_id: int) -> dict[str, Any]:
    return {
        "import_job_id": job_id,
        "applied": 0,
        "failed": 0,
        "skipped_hold": 0,
        "skipped_not_ready": 0,
        "results": [],
    }


def _merge_bulk_group(combined: dict[str, Any], bulk_out: dict[str, Any]) -> None:
    for r in bulk_out.get("results") or []:
        cid = int(r["candidate_id"])
        if r.get("ok"):
            combined["applied"] += 1
            combined["results"].append(
                {"candidate_id": cid, "status": "applied", "result": r.get("result")}
            )
        else:
            combined["failed"] += 1
            combined["results"].append(
                {
                    "candidate_id": cid,
                    "status": "failed",
                    "detail": r.get("detail") or "bulk apply failed",
                }
            )


def _merge_plan_apply_out(combined: dict[str, Any], part_out: dict[str, Any]) -> None:
    combined["applied"] += int(part_out.get("applied") or 0)
    combined["failed"] += int(part_out.get("failed") or 0)
    combined["skipped_hold"] += int(part_out.get("skipped_hold") or 0)
    combined["skipped_not_ready"] += int(part_out.get("skipped_not_ready") or 0)
    combined["results"].extend(part_out.get("results") or [])


def _classify_plan_rows(
    candidate_ids: list[int],
    rows_by_cid: dict[int, dict[str, Any]],
    combined: dict[str, Any],
) -> tuple[
    list[int],
    list[dict[str, Any]],
    dict[int, list[int]],
    dict[int, list[int]],
    list[int],
    list[int],
]:
    provisional_cids: list[int] = []
    per_candidate_geo: list[dict[str, Any]] = []
    map_customer_groups: dict[int, list[int]] = defaultdict(list)
    map_distributor_groups: dict[int, list[int]] = defaultdict(list)
    ignore_cids: list[int] = []
    fallback_cids: list[int] = []

    for cid in candidate_ids:
        row = rows_by_cid.get(int(cid))
        if row is None:
            combined["failed"] += 1
            combined["results"].append(
                {
                    "candidate_id": int(cid),
                    "status": "failed",
                    "detail": "Candidate not found in effective plan",
                }
            )
            continue
        if row.get("hold_for_manual_review"):
            combined["skipped_hold"] += 1
            combined["results"].append(
                {"candidate_id": int(cid), "status": "skipped_hold", "detail": "hold_for_manual_review"}
            )
            continue
        if not row.get("ready"):
            combined["skipped_not_ready"] += 1
            blockers = row.get("resolution_blockers")
            detail = ",".join(blockers) if isinstance(blockers, list) and blockers else "not_ready"
            combined["results"].append(
                {"candidate_id": int(cid), "status": "skipped_not_ready", "detail": detail}
            )
            continue

        action = str(row.get("suggested_action") or "")
        if action == "create_provisional_customer":
            provisional_cids.append(int(cid))
            geo_entry: dict[str, Any] = {"candidate_id": int(cid)}
            er = row.get("effective_region_id")
            ec = row.get("effective_channel_id")
            if er is not None:
                geo_entry["region_id"] = int(er)
            if ec is not None:
                geo_entry["channel_id"] = int(ec)
            if len(geo_entry) > 1:
                per_candidate_geo.append(geo_entry)
        elif action == "map_customer":
            tid = row.get("suggested_target_id")
            if tid is None:
                combined["failed"] += 1
                combined["results"].append(
                    {
                        "candidate_id": int(cid),
                        "status": "failed",
                        "detail": "Plan missing customer target",
                    }
                )
            else:
                map_customer_groups[int(tid)].append(int(cid))
        elif action == "map_distributor":
            tid = row.get("suggested_target_id")
            if tid is None:
                combined["failed"] += 1
                combined["results"].append(
                    {
                        "candidate_id": int(cid),
                        "status": "failed",
                        "detail": "Plan missing distributor target",
                    }
                )
            else:
                map_distributor_groups[int(tid)].append(int(cid))
        elif action == "ignore":
            ignore_cids.append(int(cid))
        else:
            fallback_cids.append(int(cid))

    return (
        provisional_cids,
        per_candidate_geo,
        dict(map_customer_groups),
        dict(map_distributor_groups),
        ignore_cids,
        fallback_cids,
    )


def run_dsi_resolution_plan_apply_orchestrator(
    session: Session,
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Build effective plan once, route ready rows to bulk sync writers."""
    candidate_ids: list[int] = [int(x) for x in payload.get("candidate_ids") or []]
    default_region_id = payload.get("default_region_id")
    default_channel_id = payload.get("default_channel_id")
    default_region_id = int(default_region_id) if default_region_id is not None else None
    default_channel_id = int(default_channel_id) if default_channel_id is not None else None
    partner_tier = payload.get("partner_tier")
    provisional_notes_summary = payload.get("provisional_notes_summary")
    confirm = bool(payload.get("confirm_for_suspicious_distributor_token"))
    overrides_raw = payload.get("overrides") or []
    overrides: list[dict[str, Any]] = [dict(o) for o in overrides_raw if isinstance(o, dict)]

    total = len(candidate_ids)
    combined = _empty_combined(job_id)
    processed = 0

    def _checkpoint() -> None:
        _persist_dsi_steward_apply_checkpoint(
            job_id,
            processed=processed,
            total=total,
            applied=int(combined["applied"]),
            failed=int(combined["failed"]),
        )

    def _advance(count: int) -> None:
        nonlocal processed
        processed = min(total, processed + count)
        if on_progress is not None:
            on_progress(processed, total)
        _checkpoint()

    plan = build_dsi_resolution_plan_effective_sync(
        session,
        job_id,
        candidate_ids=candidate_ids,
        default_region_id=default_region_id,
        default_channel_id=default_channel_id,
        overrides=overrides,
        global_confirm_suspicious_distributor=confirm,
    )
    rows_by_cid = {
        int(r["candidate_id"]): r for r in plan.get("rows") or [] if "candidate_id" in r
    }

    (
        provisional_cids,
        per_candidate_geo,
        map_customer_groups,
        map_distributor_groups,
        ignore_cids,
        fallback_cids,
    ) = _classify_plan_rows(candidate_ids, rows_by_cid, combined)

    if provisional_cids:
        prov_out = run_dsi_bulk_provisional_customers_sync(
            session,
            job_id,
            {
                "candidate_ids": provisional_cids,
                "region_id": default_region_id,
                "channel_id": default_channel_id,
                "per_candidate_geo": per_candidate_geo,
                "partner_tier": partner_tier,
                "provisional_notes_summary": provisional_notes_summary,
            },
            on_progress=on_progress,
        )
        _merge_bulk_group(combined, prov_out)
        _advance(len(provisional_cids))

    for customer_id, cids in sorted(map_customer_groups.items()):
        map_out = run_dsi_bulk_map_customers_sync(
            session,
            job_id,
            customer_id=int(customer_id),
            candidate_ids=cids,
        )
        _merge_bulk_group(combined, map_out)
        _advance(len(cids))

    for distributor_id, cids in sorted(map_distributor_groups.items()):
        dist_out = run_dsi_bulk_map_distributors_sync(
            session,
            job_id,
            distributor_id=int(distributor_id),
            candidate_ids=cids,
        )
        _merge_bulk_group(combined, dist_out)
        _advance(len(cids))

    if ignore_cids:
        ign_out = run_dsi_bulk_ignore_sync(session, job_id, ignore_cids)
        _merge_bulk_group(combined, ign_out)
        _advance(len(ignore_cids))

    if fallback_cids:
        logger.info(
            "dsi_resolution_plan_apply fallback per-row path job_id=%s count=%s",
            job_id,
            len(fallback_cids),
        )

        async def _fallback_apply() -> dict[str, Any]:
            async with AsyncSessionLocal() as db:
                prod_idx = await db.run_sync(_load_product_resolution_index)
                return await apply_dsi_resolution_plan_rows(
                    db,
                    job_id,
                    fallback_cids,
                    default_region_id=default_region_id,
                    default_channel_id=default_channel_id,
                    partner_tier=partner_tier,
                    provisional_notes_summary=provisional_notes_summary,
                    confirm_for_suspicious_distributor_token=confirm,
                    overrides=overrides,
                    product_index=prod_idx,
                )

        fb_out = asyncio.run(_fallback_apply())
        _merge_plan_apply_out(combined, fb_out)
        _advance(len(fallback_cids))

    processed = total
    if on_progress is not None:
        on_progress(total, total)
    _checkpoint()
    return _finalize_apply_result(combined, processed=processed, total=total)


def run_dsi_resolution_plan_apply_sync(
    job_id: int,
    payload: dict[str, Any],
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Celery entry: sync orchestrator with bulk commits (not per-row replan loop)."""
    candidate_ids: list[int] = [int(x) for x in payload.get("candidate_ids") or []]
    total = len(candidate_ids)
    try:
        with SessionLocal() as session:
            combined = run_dsi_resolution_plan_apply_orchestrator(
                session, job_id, payload, on_progress=on_progress
            )
            return _finalize_apply_result(combined, processed=total, total=total)
    except Exception as exc:
        logger.exception("dsi_resolution_plan_apply failed job_id=%s", job_id)
        ckpt = _read_dsi_steward_apply_checkpoint(job_id) or {}
        processed = int(ckpt.get("processed") or 0)
        if processed <= 0:
            raise
        err_msg = str(exc)
        _persist_dsi_steward_apply_checkpoint(
            job_id,
            processed=processed,
            total=int(ckpt.get("total") or total),
            applied=int(ckpt.get("applied") or 0),
            failed=int(ckpt.get("failed") or 0),
            interrupted=True,
            error=err_msg,
        )
        combined = _empty_combined(job_id)
        combined["applied"] = int(ckpt.get("applied") or 0)
        combined["failed"] = int(ckpt.get("failed") or 0)
        return _finalize_apply_result(
            combined,
            processed=processed,
            total=int(ckpt.get("total") or total),
            interrupted=True,
            error=err_msg,
        )
