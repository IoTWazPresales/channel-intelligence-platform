from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cip",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Tasks use explicit ``name=`` (e.g. ``imports.process_job``), not ``app.worker.tasks.*``.
# Route them to the default worker queue (``celery worker`` without ``-Q`` consumes ``celery``).
celery_app.conf.task_routes = {
    "imports.process_job": {"queue": "celery"},
    "imports.infer_dsi": {"queue": "celery"},
    "imports.product_master_commit": {"queue": "celery"},
    "imports.dsi_bulk_provisional_customers": {"queue": "celery"},
    "imports.dsi_resolution_plan_apply": {"queue": "celery"},
}

import app.worker.tasks  # noqa: E402, F401 — register tasks
