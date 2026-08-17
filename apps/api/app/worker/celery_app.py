from celery import Celery
from celery.schedules import crontab, schedule
from celery.signals import worker_ready
import logging
import os

from app.core.config import get_settings
from app.services.report_schedule_runner import report_schedule_poll_interval_seconds
from app.worker.celery_queues import build_task_routes, dev_beat_disabled
from app.worker.code_pin import describe_worker_code_pin
from app.worker.ledger_task import LedgerTask

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "cip",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.Task = LedgerTask

celery_app.conf.task_track_started = True


def build_beat_schedule() -> dict:
    """Celery beat entries when beat is enabled (Docker/prod, or CIP_ENABLE_DEV_BEAT=1).

    Calendar report cadence still lives on ``report_schedule.next_run_at``. The reports
    task is an interval so a beat process that was down over Monday 07:00 UTC still
    notices overdue rows on the next tick — same catch-up contract as the API poller.
    """
    return {
        "imports-reap-stale-running-jobs": {
            "task": "imports.reap_stale_running_jobs",
            "schedule": schedule(
                run_every=float(os.environ.get("CIP_RUNNING_JOB_REAPER_INTERVAL_SECONDS", "120"))
            ),
        },
        # CST expected-report tracker (spec §10.4.4.5): due Mon / late Tue / missing thereafter.
        # Daily morning pass is enough; advance_cst_report_slots is idempotent.
        "cst-advance-report-slots": {
            "task": "imports.cst_advance_report_slots",
            "schedule": crontab(hour=6, minute=15),
        },
        # Listing Capture poller (LC-U1): gated no-op unless schedule enabled + listings exist.
        "listing-capture-poll": {
            "task": "listing_capture.poll_listings",
            "schedule": crontab(minute="*/30"),
        },
        # BACKLOG-098: deliver due calendar schedules (including catch-up).
        # Only delivers ReportSchedule rows with enabled=True (config/opt-in).
        "reports-run-due-schedules": {
            "task": "reports.run_due_schedules",
            "schedule": schedule(run_every=float(report_schedule_poll_interval_seconds())),
        },
    }


# Periodic maintenance — local dev: `pnpm dev:worker` (Unix: worker --beat; Windows: sibling beat process).
# Docker/prod: separate `beat` service in docker-compose.
# Windows solo dev disables beat by default (BACKLOG-038); set CIP_ENABLE_DEV_BEAT=1 to re-enable.
# Daily Windows topology (`pnpm dev:api-web`) has no beat — API lifespan poller catch-up covers 098.
if dev_beat_disabled():
    celery_app.conf.beat_schedule = {}
else:
    celery_app.conf.beat_schedule = build_beat_schedule()

# Interactive steward tasks vs batch validate/apply (BACKLOG-039). Workers must subscribe with
# ``-Q interactive,batch,celery`` (interactive first) — see scripts/dev-worker.js and docker-compose.
celery_app.conf.task_routes = build_task_routes()

import app.worker.tasks  # noqa: E402, F401 — register tasks


@worker_ready.connect
def _log_worker_code_pin(**_kwargs) -> None:
    # BACKLOG-111: restart this process after lineup parser commits; pin is in worker logs.
    logger.info("%s", describe_worker_code_pin())
