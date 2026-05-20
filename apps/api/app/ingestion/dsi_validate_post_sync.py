"""Post-run hook for DSI validate — currently a no-op pending sync rewrite of auto-apply.

The original post-validation steps were:
  1. ``apply_dsi_resolution_plan_rows`` — historical auto-apply of obvious mapping candidates.
  2. ``refresh_dsi_staging_lines_for_job`` — re-resolve staging lines AFTER #1 changed mappings.

Both are disabled:
  - #1 requires ``asyncio.run()`` inside a Celery solo-pool task on Windows, which hangs.
  - #2 is only meaningful after #1 changes mappings; running it immediately after a fresh
    validation is a full redundant per-row resolution pass (N×DB-queries with no benefit).

Resolution candidates remain at ``needs_review``. The steward panel or an explicit
``POST .../dsi-apply`` call handles them.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def run_dsi_validate_post_import_orchestration(sync_db: Session, job_id: int) -> None:  # noqa: ARG001
    """No-op placeholder — post-validation orchestration deferred pending sync rewrite."""
    logger.debug("run_dsi_validate_post_import_orchestration: no-op for job_id=%s", job_id)
