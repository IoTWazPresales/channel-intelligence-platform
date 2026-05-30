"""Sync Celery entrypoint for current lineup case parse (wraps async parser)."""

from __future__ import annotations

import asyncio
import base64
import logging

logger = logging.getLogger(__name__)

ASYNC_PARSE_ROW_THRESHOLD = 500
ASYNC_PARSE_BYTE_THRESHOLD = 512 * 1024


def run_lineup_case_parse_sync(
    case_id: int,
    filename: str,
    file_bytes: bytes,
    *,
    import_job_id: int | None = None,
) -> dict:
    """Run parse_current_lineup_file in a fresh event loop (Celery worker safe)."""
    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file

    async def _run() -> dict:
        async with AsyncSessionLocal() as db:
            result = await parse_current_lineup_file(
                db,
                case_id,
                filename,
                file_bytes,
                existing_import_job_id=import_job_id,
            )
            return {
                "case_id": result.case_id,
                "import_job_id": result.import_job_id,
                "total_rows": result.total_rows,
                "resolved_products": result.resolved_products,
                "unresolved_products": result.unresolved_products,
                "line_count": result.line_count,
                "warnings": result.warnings,
            }

    return asyncio.run(_run())


def run_lineup_case_parse_job(
    case_id: int,
    filename: str,
    file_b64: str,
    import_job_id: int,
    *,
    celery_task_id: str | None = None,
) -> dict:
    """Celery worker entry: decode payload and parse lineup file."""
    _ = celery_task_id
    file_bytes = base64.standard_b64decode(file_b64.encode("ascii"))
    try:
        return run_lineup_case_parse_sync(
            case_id,
            filename,
            file_bytes,
            import_job_id=import_job_id,
        )
    except Exception:
        logger.exception("lineup parse failed case_id=%s import_job_id=%s", case_id, import_job_id)
        raise
