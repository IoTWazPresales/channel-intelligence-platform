"""HTTP-layer lineup parse orchestration (sync vs async Celery)."""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.services.commercial_planner.current_lineup_seed import CurrentLineupSourceNotConfiguredError
from app.services.commercial_planner.lineup_case_parser import (
    parse_current_lineup_file,
    preview_current_lineup_file,
)
from app.services.commercial_planner.lineup_parse_dispatch import (
    enqueue_lineup_parse_sync,
    prepare_lineup_parse_import_job_sync,
    should_parse_lineup_async,
)


async def execute_lineup_parse_upload(
    db: AsyncSession,
    case_id: int,
    filename: str,
    file_bytes: bytes,
) -> dict | JSONResponse:
    """Parse upload: sync 200 or async 202 when file exceeds thresholds."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status not in ("draft_imported",):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Can only parse-upload to cases with status 'draft_imported'. "
                f"Current: '{case.commercial_status}'"
            ),
        )

    existing_count = (
        await db.execute(
            select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case_id)
        )
    ).scalar_one()
    if existing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This case already has {existing_count} lines. "
                "Delete the case and create a new one to re-upload."
            ),
        )

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        preview = await preview_current_lineup_file(db, filename, file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parse preview failed: {exc}") from exc

    if not preview.can_apply:
        raise HTTPException(
            status_code=422,
            detail="No products could be resolved from this file. Fix SKUs and preview again.",
        )

    if should_parse_lineup_async(file_bytes=file_bytes, preview_total_rows=preview.total_rows):
        with SessionLocal() as sync_db:
            job = prepare_lineup_parse_import_job_sync(sync_db, case_id=case_id, filename=filename)
            sync_db.commit()
            import_job_id = int(job.id)
        out = enqueue_lineup_parse_sync(
            case_id=case_id,
            filename=filename,
            file_bytes=file_bytes,
            import_job_id=import_job_id,
        )
        if out.get("outcome") == "dispatch_failed":
            raise HTTPException(
                status_code=503,
                detail={
                    "message": out.get("message", "Lineup parse dispatch failed"),
                    "code": "lineup_parse_dispatch_failed",
                },
            )
        return JSONResponse(
            status_code=int(out.get("http_status", 202)),
            content={
                "case_id": case_id,
                "import_job_id": import_job_id,
                "lineup_parse": {
                    "outcome": "enqueued",
                    "task_id": out.get("task_id"),
                    "async_poll": True,
                },
                "preview": {
                    "total_rows": preview.total_rows,
                    "resolved_products": preview.resolved_products,
                    "unresolved_products": preview.unresolved_products,
                },
            },
        )

    try:
        result = await parse_current_lineup_file(db, case_id, filename, file_bytes)
    except CurrentLineupSourceNotConfiguredError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "current_lineup_import_not_seeded",
                "message": str(exc),
                "remediation": exc.remediation,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parse failed: {exc}") from exc

    return {
        "case_id": result.case_id,
        "import_job_id": result.import_job_id,
        "total_rows": result.total_rows,
        "resolved_products": result.resolved_products,
        "unresolved_products": result.unresolved_products,
        "line_count": result.line_count,
        "warnings": result.warnings,
        "lineup_parse": {"outcome": "completed", "async_poll": False},
    }
