"""Sync Celery entrypoint for current lineup case parse (wraps async parser)."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

ASYNC_PARSE_ROW_THRESHOLD = 500
ASYNC_PARSE_BYTE_THRESHOLD = 512 * 1024


def run_lineup_case_parse_sync(case_id: int, filename: str, file_bytes: bytes) -> dict:
    """Run parse_current_lineup_file in a fresh event loop (Celery worker safe)."""
    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file

    async def _run() -> dict:
        async with AsyncSessionLocal() as db:
            result = await parse_current_lineup_file(db, case_id, filename, file_bytes)
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
