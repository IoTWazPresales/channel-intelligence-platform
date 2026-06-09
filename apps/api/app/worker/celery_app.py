from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "cip",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_track_started = True

# Tasks use explicit ``name=`` (e.g. ``imports.process_job``), not ``app.worker.tasks.*``.
# Route them to the default worker queue (``celery worker`` without ``-Q`` consumes ``celery``).
celery_app.conf.task_routes = {
    "imports.process_job": {"queue": "celery"},
    "imports.infer_dsi": {"queue": "celery"},
    "imports.product_master_commit": {"queue": "celery"},
    "imports.product_master_validate": {"queue": "celery"},
    "imports.dsi_bulk_provisional_customers": {"queue": "celery"},
    "imports.dsi_resolution_plan_apply": {"queue": "celery"},
    "imports.dsi_resolution_plan_compute": {"queue": "celery"},
    "imports.dsi_apply": {"queue": "celery"},
    "imports.shipment_apply": {"queue": "celery"},
    "imports.shipment_bulk_map_customer": {"queue": "celery"},
    "imports.shipment_bulk_apply_plans": {"queue": "celery"},
    "imports.shipment_bulk_provisional_customers": {"queue": "celery"},
    "imports.dsi_soh_reconciliation": {"queue": "celery"},
    "imports.dsi_velocity_compute": {"queue": "celery"},
    "imports.dsi_forecasting": {"queue": "celery"},
    "commercial_planner.parse_lineup_case": {"queue": "celery"},
}

import app.worker.tasks  # noqa: E402, F401 — register tasks
