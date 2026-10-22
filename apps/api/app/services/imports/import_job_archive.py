"""Archive or unarchive import jobs by id (Warren 2026-10-22, N-0113).

Archiving sets ``archived_at``; unarchiving clears it. Nothing else changes: the job keeps its
status, its staging and every row it loaded. An archived job is hidden from the Import Center list
(unless "Show archived" is on) and from the failed-import counts on Attention, Brief and Ops.
The preview lists each job with its status and whether it would change; the confirm writes one
``platform_audit_event`` with the ids.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.services.imports.import_job_bulk_delete import MAX_JOBS, normalize_job_ids


def _jobs(db: Session, ids: list[int]) -> list[ImportJob]:
    return list(db.scalars(select(ImportJob).where(ImportJob.id.in_(ids)).order_by(ImportJob.id)).all())


def preview_import_job_archive(db: Session, job_ids: list[int], *, archive: bool) -> dict[str, Any]:
    """Each job with its status and whether archiving (or unarchiving) would change it. Writes nothing."""
    ids = normalize_job_ids(job_ids)
    jobs = _jobs(db, ids)
    found = {j.id for j in jobs}
    rows = [
        {
            "id": j.id,
            "file_name": j.file_name,
            "template_slug": j.template_slug,
            "status": j.status,
            "stage": j.stage,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "archived_at": j.archived_at.isoformat() if j.archived_at else None,
            "will_change": (j.archived_at is None) if archive else (j.archived_at is not None),
        }
        for j in jobs
    ]
    return {
        "action": "archive" if archive else "unarchive",
        "job_ids": ids,
        "missing_job_ids": [i for i in ids if i not in found],
        "jobs": rows,
        "to_change": sum(1 for r in rows if r["will_change"]),
        "unchanged": sum(1 for r in rows if not r["will_change"]),
        "max_jobs": MAX_JOBS,
    }


def set_import_jobs_archived(
    db: Session, job_ids: list[int], *, archive: bool, user: dict | None = None
) -> dict[str, Any]:
    """Archive (or unarchive) the jobs and write the audit event. The caller commits.

    Raises ``ValueError("not_all_jobs_found")`` when an id does not exist, so nothing changes.
    """
    from app.services.platform_audit import record_platform_audit_sync

    ids = normalize_job_ids(job_ids)
    if not ids:
        raise ValueError("no_valid_job_ids")
    jobs = _jobs(db, ids)
    if len(jobs) != len(ids):
        raise ValueError("not_all_jobs_found")
    changing = [j.id for j in jobs if (j.archived_at is None) == archive]
    if changing:
        db.execute(
            update(ImportJob)
            .where(ImportJob.id.in_(changing))
            .values(archived_at=datetime.now(timezone.utc) if archive else None)
            .execution_options(synchronize_session=False)
        )
    action = "archive" if archive else "unarchive"
    record_platform_audit_sync(
        db,
        user,
        area="admin",
        action=f"import_jobs_{action}",
        target_type="import_job",
        target_id=",".join(map(str, ids))[:128],
        detail={
            "job_ids": ids,
            "changed_ids": changing,
            "unchanged_ids": [i for i in ids if i not in set(changing)],
        },
    )
    return {"action": action, "job_ids": ids, "changed_ids": changing, "changed": len(changing),
            "unchanged": len(ids) - len(changing)}
