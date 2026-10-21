"""N-0086 one-off editor: adds role gates to apps/api/app/api/v1/endpoints/imports.py (exact-match replacements)."""

import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
p = os.path.join(ROOT, "apps", "api", "app", "api", "v1", "endpoints", "imports.py")
s = open(p, encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, (old, n)
    s = s.replace(old, new)


rep(
    '''router = APIRouter()
logger = logging.getLogger(__name__)
''',
    '''router = APIRouter()
logger = logging.getLogger(__name__)

# N-0086 role gates (reads stay sign-in only; the router already requires sign-in).
# Steward writes: resolve / map / ignore candidates, bulk steward actions, resolution plans and the
# DSI / CST / shipment pipeline steps. Admin always passes require_roles.
_STEWARD_WRITE = [Depends(require_roles(Role.ADMIN, Role.STEWARD))]
# Upload / process / cancel / retry: viewers never; planners only on the job templates they own
# (checked per job by require_import_template_role); stewards and admins on every template.
_IMPORT_RUNNER = [Depends(require_roles(Role.ADMIN, Role.STEWARD, Role.PLANNER))]
# CPOR uploads only stage rows; every CPOR write after that is gated again on the CPOR routers (N-0038).
PLANNER_UPLOAD_TEMPLATES = frozenset({"cpor_historical_cases", "cpor_payment_evidence"})
# Lineup jobs are created by the commercial-planner routes; planners may cancel or retry them.
PLANNER_RUN_TEMPLATES = PLANNER_UPLOAD_TEMPLATES | frozenset(
    {"current_lineup", "unified_lineup", "bulk_lineup_backfill"}
)
_IMPORT_STEWARD_ROLES = frozenset({Role.ADMIN, Role.STEWARD})


def require_import_template_role(
    user: dict | None, template_slug: str | None, planner_templates: frozenset[str]
) -> None:
    """403 unless the user is steward/admin, or a planner acting on a template they own."""
    role = (user or {}).get("role")
    if role in _IMPORT_STEWARD_ROLES:
        return
    if role == Role.PLANNER and (template_slug or "").strip() in planner_templates:
        return
    raise HTTPException(status_code=403, detail="Insufficient role")
''',
)

steward_paths = [
    '"/jobs/{job_id}/dsi-file-exclusions"',
    '"/jobs/{job_id}/dsi-file-distributors"',
    '"/jobs/{job_id}/dsi-file-snapshot-periods"',
    '"/dsi/batch-propose"',
    '"/dsi/batch-jobs"',
    '"/cst/batch-propose"',
    '"/cst/batch-jobs"',
    '"/jobs/{job_id}/shipment-sheets"',
    '"/jobs/{job_id}/shipment-validate"',
    '"/jobs/{job_id}/dsi-validate"',
    '"/jobs/{job_id}/dsi-apply"',
]
for sp in steward_paths:
    rep(f"@router.post({sp})\n", f"@router.post({sp}, dependencies=_STEWARD_WRITE)\n")
for sp in ['"/jobs/{job_id}/shipment-field-mapping"', '"/jobs/{job_id}/dsi-field-mapping"']:
    rep(f"@router.put({sp})\n", f"@router.put({sp}, dependencies=_STEWARD_WRITE)\n")
for sp in [
    '"/jobs/{job_id}/cst-candidates/{candidate_id}/resolve"',
    '"/jobs/{job_id}/cst-candidates/{candidate_id}/ignore"',
    '"/jobs/{job_id}/cst-steward-bulk-preview"',
    '"/jobs/{job_id}/cst-steward-bulk-apply"',
    '"/jobs/{job_id}/cst-resolution-plan"',
]:
    rep(
        f"@router.post({sp}, status_code=200)\n",
        f"@router.post({sp}, status_code=200, dependencies=_STEWARD_WRITE)\n",
    )
for sp in [
    '"/jobs/{job_id}/cst-steward-bulk-ignore/apply-async"',
    '"/jobs/{job_id}/cst-resolution-plan/compute-async"',
    '"/jobs/{job_id}/cst-resolution-plan/apply-async"',
]:
    rep(
        f"@router.post({sp}, status_code=202)\n",
        f"@router.post({sp}, status_code=202, dependencies=_STEWARD_WRITE)\n",
    )
rep(
    '@router.post("/jobs/{job_id}/cst-steward-bulk-provisional-customers/apply-async", status_code=400)\n',
    '@router.post(\n    "/jobs/{job_id}/cst-steward-bulk-provisional-customers/apply-async",\n'
    "    status_code=400,\n    dependencies=_STEWARD_WRITE,\n)\n",
)

rep(
    '@router.post("/jobs")\nasync def create_job(',
    '@router.post("/jobs", dependencies=_IMPORT_RUNNER)\nasync def create_job(',
)
rep(
    '''    tpl = source.import_template
    if not tpl or not tpl.enabled:
        raise HTTPException(status_code=400, detail="Source has no active import template")

    mode = (import_mode or "").strip().lower()''',
    '''    tpl = source.import_template
    if not tpl or not tpl.enabled:
        raise HTTPException(status_code=400, detail="Source has no active import template")
    require_import_template_role(user, tpl.slug, PLANNER_UPLOAD_TEMPLATES)

    mode = (import_mode or "").strip().lower()''',
)

rep(
    '''@router.post("/jobs/{job_id}/cancel")
async def post_cancel_import_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Revoke Celery work, clear task metadata, mark job failed (works for stale queued refs too)."""
    import asyncio

    from app.services.imports.import_job_task_control import cancel_import_job_sync

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
''',
    '''@router.post("/jobs/{job_id}/cancel", dependencies=_IMPORT_RUNNER)
async def post_cancel_import_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Revoke Celery work, clear task metadata, mark job failed (works for stale queued refs too)."""
    import asyncio

    from app.services.imports.import_job_task_control import cancel_import_job_sync

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    require_import_template_role(user, job.template_slug, PLANNER_RUN_TEMPLATES)
''',
)
rep(
    '''@router.post("/jobs/{job_id}/retry")
async def post_retry_import_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Re-enqueue ``imports.process_job`` for a failed job (same pattern as validate/revalidate)."""
    import asyncio

    from app.services.imports.import_job_task_control import prepare_import_job_retry_sync

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
''',
    '''@router.post("/jobs/{job_id}/retry", dependencies=_IMPORT_RUNNER)
async def post_retry_import_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Re-enqueue ``imports.process_job`` for a failed job (same pattern as validate/revalidate)."""
    import asyncio

    from app.services.imports.import_job_task_control import prepare_import_job_retry_sync

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    require_import_template_role(user, job.template_slug, PLANNER_RUN_TEMPLATES)
''',
)
rep(
    '''@router.post("/jobs/{job_id}/process")
async def process_job(job_id: int):
    import asyncio
''',
    '''@router.post("/jobs/{job_id}/process", dependencies=_IMPORT_RUNNER)
async def process_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    import asyncio

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    require_import_template_role(user, job.template_slug, PLANNER_UPLOAD_TEMPLATES)
''',
)
open(p, "w", encoding="utf-8", newline="").write(s)
print("imports.py edited")
