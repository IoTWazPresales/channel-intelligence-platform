from celery import Celery
from celery.schedules import crontab, schedule
import os

from app.core.config import get_settings
from app.worker.celery_queues import build_task_routes, dev_beat_disabled
from app.worker.ledger_task import LedgerTask

settings = get_settings()

celery_app = Celery(
    "cip",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.Task = LedgerTask

celery_app.conf.task_track_started = True

# Periodic maintenance — local dev: `pnpm dev:worker` (Unix: worker --beat; Windows: sibling beat process).
# Docker/prod: separate `beat` service in docker-compose.
# Windows solo dev disables beat by default (BACKLOG-038); set CIP_ENABLE_DEV_BEAT=1 to re-enable.
if dev_beat_disabled():
    celery_app.conf.beat_schedule = {}
else:
    celery_app.conf.beat_schedule = {
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
    }

# Interactive steward tasks vs batch validate/apply (BACKLOG-039). Workers must subscribe with
# ``-Q interactive,batch,celery`` (interactive first) — see scripts/dev-worker.js and docker-compose.
celery_app.conf.task_routes = build_task_routes()

import app.worker.tasks  # noqa: E402, F401 — register tasks
