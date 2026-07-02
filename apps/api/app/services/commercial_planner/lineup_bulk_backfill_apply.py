"""Bulk lineup backfill batch apply — creates cases + dispatches parse jobs (Spec C Step B)."""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase
from app.models.ingestion import ImportJob
from app.services.commercial_planner.current_lineup_seed import ensure_lineup_import_seed
from app.services.commercial_planner.lineup_bulk_backfill_preview import (
    BULK_SOURCE_CODE,
    BULK_TEMPLATE_SLUG,
)
from app.services.commercial_planner.lineup_period_canonical import display_period_label_from_period_start
from app.services.commercial_planner.lineup_parse_dispatch import (
    enqueue_lineup_parse_sync,
    prepare_lineup_parse_import_job_sync,
)
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


async def persist_preview_session(
    db: AsyncSession,
    preview_payload: dict[str, Any],
) -> ImportJob:
    """Store preview on an ImportJob (no lineup writes)."""
    from app.models.ingestion import ImportTemplate, SourceDefinition

    await ensure_lineup_import_seed(db, template_slug=BULK_TEMPLATE_SLUG, source_code=BULK_SOURCE_CODE)
    source = (
        await db.execute(
            select(SourceDefinition)
            .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
            .where(ImportTemplate.slug == BULK_TEMPLATE_SLUG, SourceDefinition.code == BULK_SOURCE_CODE)
            .limit(1)
        )
    ).scalar_one_or_none()
    if source is None:
        raise ValueError("bulk_lineup_backfill source is not configured")

    now = datetime.now(timezone.utc)
    job = ImportJob(
        source_id=source.id,
        template_slug=BULK_TEMPLATE_SLUG,
        import_mode="preview",
        status="validated",
        file_name=f"bulk_lineup_preview_{preview_payload.get('preview_id', 'session')}",
        started_at=now,
        completed_at=now,
        stage="validated",
        staged_metadata=to_jsonable({"bulk_lineup_backfill_preview": preview_payload}),
    )
    db.add(job)
    await db.flush()
    preview_payload["session_import_job_id"] = int(job.id)
    job.staged_metadata = to_jsonable({"bulk_lineup_backfill_preview": preview_payload})
    await db.commit()
    await db.refresh(job)
    return job


async def load_preview_session(db: AsyncSession, session_job_id: int) -> dict[str, Any]:
    job = await db.get(ImportJob, session_job_id)
    if job is None:
        raise ValueError(f"Preview session import_job_id={session_job_id} not found")
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    preview = meta.get("bulk_lineup_backfill_preview")
    if not isinstance(preview, dict):
        raise ValueError("Preview session payload missing")
    return preview


def _file_bytes_by_key(preview: dict[str, Any]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for entry in preview.get("file_manifest") or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("file_key")
        b64 = entry.get("b64")
        if key and b64:
            out[str(key)] = base64.standard_b64decode(str(b64).encode("ascii"))
    return out


def _winner_proposal_keys(preview: dict[str, Any], confirmations: dict[str, str] | None) -> set[str]:
    """Resolve supersession winners — steward confirmation overrides default latest-wins."""
    winners: set[str] = set()
    confirmations = confirmations or {}
    for group in preview.get("supersession_collisions") or []:
        if not isinstance(group, dict):
            continue
        gkey = str(group.get("supersession_group_key") or "")
        if gkey in confirmations:
            winners.add(str(confirmations[gkey]))
        else:
            w = group.get("winner_proposal_key")
            if w:
                winners.add(str(w))
    return winners


def _loser_proposal_keys(preview: dict[str, Any], winners: set[str]) -> set[str]:
    losers: set[str] = set()
    for group in preview.get("supersession_collisions") or []:
        if not isinstance(group, dict):
            continue
        for member in group.get("members") or []:
            if not isinstance(member, dict):
                continue
            pk = str(member.get("proposal_key") or "")
            if pk and pk not in winners:
                losers.add(pk)
    return losers


def _applied_proposal_map(meta: dict[str, Any]) -> dict[str, int]:
    apply_meta = meta.get("bulk_lineup_backfill_apply")
    if not isinstance(apply_meta, dict):
        return {}
    raw = apply_meta.get("applied_proposal_keys")
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items()}


def _winner_case_by_group(applied: dict[str, int], preview: dict[str, Any]) -> dict[str, int]:
    """Map supersession_group_key → active winner case_id from prior apply."""
    prop_by_key = {
        str(p.get("proposal_key")): p
        for p in (preview.get("case_proposals") or [])
        if isinstance(p, dict) and p.get("proposal_key")
    }
    winners = _winner_proposal_keys(preview, None)
    out: dict[str, int] = {}
    for pk, case_id in applied.items():
        if pk not in winners:
            continue
        prop = prop_by_key.get(pk)
        if not prop:
            continue
        sgk = str(prop.get("supersession_group_key") or "")
        if sgk:
            out[sgk] = case_id
    return out


def _create_case_and_maybe_parse(
    db: Session,
    *,
    prop: dict[str, Any],
    file_bytes: bytes | None,
    preview: dict[str, Any],
    commercial_plan_id: int | None,
    superseded_by_case_id: int | None,
    enqueue_parse: bool,
) -> tuple[int, str]:
    filename = str(prop.get("filename") or "upload")
    sheet_name = str(prop.get("sheet_name") or "") or None
    status = "superseded" if superseded_by_case_id is not None else "draft_imported"

    ps = _parse_iso_date(prop.get("period_start"))
    display_label = (
        display_period_label_from_period_start(ps) if ps is not None else prop.get("period_label")
    )

    case = CommercialLineupCase(
        commercial_plan_id=commercial_plan_id,
        file_name=filename,
        period_label=display_label,
        inferred_period_start=ps,
        business_unit=prop.get("business_unit"),
        product_line=prop.get("business_unit"),
        commercial_status=status,
        import_intent="historical_lineup_backfill",
        source_context="bulk_lineup_backfill",
        superseded_by_case_id=superseded_by_case_id,
        notes=f"sheet={sheet_name or 'default'}; backfill preview {preview.get('preview_id')}",
    )
    db.add(case)
    db.flush()

    outcome = "superseded_shell"
    if enqueue_parse and file_bytes is not None:
        parse_job = prepare_lineup_parse_import_job_sync(
            db,
            case_id=int(case.id),
            filename=filename,
            template_slug=BULK_TEMPLATE_SLUG,
            source_code=BULK_SOURCE_CODE,
        )
        parse_job.staged_metadata = to_jsonable(
            {
                "lineup_parse_options": {
                    "sheet_name": sheet_name,
                    "folder_path": prop.get("folder_path"),
                    "business_unit": prop.get("business_unit"),
                    "bu_report": prop.get("bu_report"),
                }
            }
        )
        db.commit()
        out = enqueue_lineup_parse_sync(
            case_id=int(case.id),
            filename=filename,
            file_bytes=file_bytes,
            import_job_id=int(parse_job.id),
            template_slug=BULK_TEMPLATE_SLUG,
            source_code=BULK_SOURCE_CODE,
        )
        outcome = str(out.get("outcome") or "enqueued")
    else:
        db.commit()

    return int(case.id), outcome


def apply_bulk_lineup_batch_sync(
    session_job_id: int,
    *,
    approved_proposal_keys: list[str] | None = None,
    excluded_proposal_keys: list[str] | None = None,
    supersession_confirmations: dict[str, str] | None = None,
    commercial_plan_id: int | None = None,
) -> dict[str, Any]:
    """Sync batch apply: create cases for approved ready proposals and enqueue parse jobs."""
    with SessionLocal() as db:
        job = db.get(ImportJob, session_job_id)
        if job is None:
            raise ValueError(f"session job {session_job_id} not found")
        meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        preview = meta.get("bulk_lineup_backfill_preview")
        if not isinstance(preview, dict):
            raise ValueError("missing preview payload")

        files_by_key = _file_bytes_by_key(preview)
        collision_winners = _winner_proposal_keys(preview, supersession_confirmations)
        collision_losers = _loser_proposal_keys(preview, collision_winners)
        excluded = set(excluded_proposal_keys or [])
        approved_set = set(approved_proposal_keys or []) if approved_proposal_keys else None

        applied_map = _applied_proposal_map(meta)
        winner_case_by_group = _winner_case_by_group(applied_map, preview)

        proposals = [p for p in (preview.get("case_proposals") or []) if isinstance(p, dict)]
        results: list[dict[str, Any]] = []
        needs_attention: list[dict[str, Any]] = []
        applied = 0
        skipped = 0

        ready_candidates: list[dict[str, Any]] = []
        for prop in proposals:
            pk = str(prop.get("proposal_key") or "")
            status = str(prop.get("status") or "")
            if status != "ready":
                needs_attention.append({**prop, "divert_reason": status})
                continue
            if pk in excluded:
                skipped += 1
                continue
            if approved_set is not None and pk not in approved_set:
                skipped += 1
                continue
            ready_candidates.append(prop)

        active_props = [p for p in ready_candidates if str(p.get("proposal_key")) not in collision_losers]
        superseded_props = [p for p in ready_candidates if str(p.get("proposal_key")) in collision_losers]

        def _record_applied(pk: str, case_id: int, outcome: str, **extra: Any) -> None:
            nonlocal applied
            applied_map[pk] = case_id
            applied += 1
            results.append({"proposal_key": pk, "outcome": outcome, "case_id": case_id, **extra})

        for prop in active_props:
            pk = str(prop.get("proposal_key") or "")
            if pk in applied_map:
                skipped += 1
                results.append({"proposal_key": pk, "outcome": "idempotent_skip", "case_id": applied_map[pk]})
                continue

            file_key = str(prop.get("file_key") or "")
            file_bytes = files_by_key.get(file_key)
            if not file_bytes:
                results.append({"proposal_key": pk, "outcome": "error", "error": "file bytes missing"})
                continue

            case_id, outcome = _create_case_and_maybe_parse(
                db,
                prop=prop,
                file_bytes=file_bytes,
                preview=preview,
                commercial_plan_id=commercial_plan_id,
                superseded_by_case_id=None,
                enqueue_parse=True,
            )
            sgk = str(prop.get("supersession_group_key") or "")
            if sgk:
                winner_case_by_group[sgk] = case_id
            _record_applied(
                pk,
                case_id,
                outcome,
                sheet_name=prop.get("sheet_name"),
                supersession_group_key=sgk or None,
            )

        for prop in superseded_props:
            pk = str(prop.get("proposal_key") or "")
            if pk in applied_map:
                skipped += 1
                results.append({"proposal_key": pk, "outcome": "idempotent_skip", "case_id": applied_map[pk]})
                continue

            sgk = str(prop.get("supersession_group_key") or "")
            winner_id = winner_case_by_group.get(sgk)
            if winner_id is None:
                results.append(
                    {
                        "proposal_key": pk,
                        "outcome": "error",
                        "error": f"supersession winner missing for group {sgk}",
                    }
                )
                continue

            case_id, outcome = _create_case_and_maybe_parse(
                db,
                prop=prop,
                file_bytes=None,
                preview=preview,
                commercial_plan_id=commercial_plan_id,
                superseded_by_case_id=winner_id,
                enqueue_parse=False,
            )
            _record_applied(
                pk,
                case_id,
                outcome,
                superseded_by_case_id=winner_id,
                supersession_group_key=sgk,
            )

        job.status = "running"
        job.import_mode = "apply"
        job.stage = "pipeline_queued"
        job.pipeline_queued_at = datetime.now(timezone.utc)
        meta = dict(meta)
        meta["bulk_lineup_backfill_apply"] = {
            "applied": applied,
            "skipped": skipped,
            "applied_proposal_keys": applied_map,
            "results": results,
            "needs_attention": needs_attention,
        }
        job.staged_metadata = to_jsonable(meta)
        db.commit()

        return {
            "session_import_job_id": session_job_id,
            "applied": applied,
            "skipped": skipped,
            "needs_attention": needs_attention,
            "results": results,
        }
