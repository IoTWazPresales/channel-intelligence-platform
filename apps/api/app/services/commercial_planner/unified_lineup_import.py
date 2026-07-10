"""Unified multi-file lineup import dispatcher (Import-Centre surface).

First-class lineup importer: accepts several files in one session and fans out **one async parse
job per file** (template_slug=``unified_lineup``), each writing its own ``CommercialLineupCase`` +
lines via the shared parser (pricing chain + period/product-line inference). Always-async so the
request returns immediately with per-file task handles; progress is visible per file in the
activity feed. One file's failure never aborts the batch.

Reuses the canonical lineup parse worker/dispatch — no second write mechanism.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase
from app.models.commercial_planner import CommercialPlan
from app.services.commercial_planner.lineup_parse_dispatch import (
    enqueue_lineup_parse_sync,
    prepare_lineup_parse_import_job_sync,
)

logger = logging.getLogger(__name__)

UNIFIED_TEMPLATE_SLUG = "unified_lineup"
UNIFIED_SOURCE_CODE = "unified_lineup_system"


async def dispatch_unified_lineup_import(
    db: AsyncSession,
    files: list[tuple[str, bytes]],
    *,
    commercial_plan_id: int | None = None,
    period_label: str | None = None,
    country_code: str | None = None,
    currency_code: str | None = None,
) -> dict[str, Any]:
    """Create one CommercialLineupCase + dispatch one async parse job per file."""
    if not files:
        return {"files": [], "file_count": 0, "dispatched": 0}

    if commercial_plan_id is not None and not await db.get(CommercialPlan, commercial_plan_id):
        # Surface as a batch-level error rather than silently dropping the linkage.
        raise ValueError(f"Unknown commercial_plan_id={commercial_plan_id}")

    results: list[dict[str, Any]] = []
    for filename, file_bytes in files:
        entry: dict[str, Any] = {"filename": filename}
        if not file_bytes:
            entry.update(outcome="error", error="Uploaded file is empty.")
            results.append(entry)
            continue
        try:
            case = CommercialLineupCase(
                commercial_plan_id=commercial_plan_id,
                period_label=period_label,
                currency_code=currency_code,
                country_code=country_code,
                file_name=filename,
                commercial_status="draft_imported",
                import_intent="current_working_lineup",
                source_context="unified_lineup_import",
            )
            db.add(case)
            await db.commit()
            await db.refresh(case)
            case_id = int(case.id)

            with SessionLocal() as sync_db:
                job = prepare_lineup_parse_import_job_sync(
                    sync_db,
                    case_id=case_id,
                    filename=filename,
                    template_slug=UNIFIED_TEMPLATE_SLUG,
                    source_code=UNIFIED_SOURCE_CODE,
                )
                sync_db.commit()
                import_job_id = int(job.id)

            out = enqueue_lineup_parse_sync(
                case_id=case_id,
                filename=filename,
                file_bytes=file_bytes,
                import_job_id=import_job_id,
                template_slug=UNIFIED_TEMPLATE_SLUG,
                source_code=UNIFIED_SOURCE_CODE,
            )
            entry.update(
                case_id=case_id,
                import_job_id=import_job_id,
                outcome=out.get("outcome"),
                task_id=out.get("task_id"),
            )
            if out.get("outcome") == "dispatch_failed":
                entry["error"] = out.get("message", "dispatch failed")
        except Exception as exc:  # noqa: BLE001 — isolate per-file failure, continue batch
            await db.rollback()
            logger.exception("unified lineup import failed for file=%s", filename)
            entry.update(outcome="error", error=str(exc))
        results.append(entry)

    dispatched = sum(1 for r in results if r.get("outcome") == "enqueued")
    return {"files": results, "file_count": len(files), "dispatched": dispatched}
