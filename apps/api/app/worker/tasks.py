import logging

from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.ingestion.pipeline import process_import_job_sync
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _write_task_level_failure(job_id: int) -> None:
    """Best-effort STAGE_FAILED writeback for exceptions that escape process_import_job_sync.

    Called when an exception is raised outside the inner try/except in the pipeline (e.g.
    RawFileMetadata not found, storage read failure, or post-processing hook failure). The inner
    handler already covers exceptions inside the pipeline try block, so this is a safety net for
    the edges that sit outside it.
    """
    from datetime import datetime, timezone

    from app.db.session_sync import SessionLocal
    from app.ingestion.pipeline import STAGE_FAILED
    from app.models.ingestion import ImportJob

    try:
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job and job.stage != STAGE_FAILED:
                job.status = "failed"
                job.stage = STAGE_FAILED
                job.error_summary = "Task-level failure; see worker log for exception detail."
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
    except Exception:
        logger.exception("STAGE_FAILED writeback also failed job_id=%s", job_id)


def run_product_master_commit_job(
    job_id: int,
    confirm_destructive: bool,
    *,
    celery_task_id: str | None,
) -> int:
    """Shared implementation for Celery worker and explicit dev-only dispatch paths."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.product_master_workflow import run_pm_commit_worker

    if celery_task_id == "dev-in-process-thread":
        DEV_CELERY_LOGGER.warning(
            "EXECUTION: Product Master commit job_id=%s running in-process (DEV ONLY, "
            "CIP_DEV_CELERY_DISPATCH=in_process_thread). Not broker-isolated.",
            job_id,
        )

    try:
        with SessionLocal() as db:
            run_pm_commit_worker(
                db,
                job_id,
                confirm_destructive=confirm_destructive,
                celery_task_id=celery_task_id,
            )
    except Exception:
        logger.exception("product_master_commit job failed job_id=%s", job_id)
        raise
    return job_id


def _persist_process_job_celery_slot(job_id: int, celery_task_id: str | None) -> None:
    """Ensure ``staged_metadata.celery_task_id`` is set for activity-feed / dsi-progress polling.

    HTTP dispatch writes this slot before the worker starts, but validate heartbeats can
    overwrite staged_metadata from an in-memory snapshot that predates that write. Re-assert
    the broker task id at worker entry so the bell and background-tasks list stay wired.
    """
    if not celery_task_id or not str(celery_task_id).strip():
        return
    from app.services.imports.import_background_slots import SLOT_MAIN, set_task_slot_by_job_id

    set_task_slot_by_job_id(job_id, SLOT_MAIN, task_id=str(celery_task_id).strip())


@celery_app.task(name="imports.process_job", bind=True)
def process_import_job_task(self, job_id: int) -> int:
    from app.db.session_sync import SessionLocal

    _persist_process_job_celery_slot(job_id, str(self.request.id) if self.request else None)

    def _on_progress(phase: str, phase_label: str, current_row: int, total_rows: int) -> None:
        try:
            from datetime import datetime, timezone

            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "phase_label": phase_label,
                    "current_row": current_row,
                    "total_rows": total_rows,
                    "pct": round(current_row / total_rows * 100) if total_rows else 0,
                    "progress_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass

    try:
        with SessionLocal() as db:
            process_import_job_sync(db, job_id, on_progress=_on_progress)
    except Exception:
        logger.exception("process_import_job_task failed job_id=%s — writing STAGE_FAILED", job_id)
        _write_task_level_failure(job_id)
        raise
    return job_id


@celery_app.task(name="imports.shipment_apply", bind=True, ack_late=True)
def shipment_apply_task(self, job_id: int) -> dict:
    """Background apply for an ``inbound_shipments`` job (auto-map → batched fact upsert → loaded)."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.shipment_apply_sync import run_shipment_apply_sync

    def _on_progress(phase: str, phase_label: str, current_row: int, total_rows: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "phase_label": phase_label,
                    "current_row": current_row,
                    "total_rows": total_rows,
                    "pct": round(current_row / total_rows * 100) if total_rows else 0,
                },
            )
        except Exception:
            pass

    try:
        with SessionLocal() as db:
            result = run_shipment_apply_sync(db, job_id, on_progress=_on_progress)
            if result.get("outcome") == "failed":
                return result
            return result
    except Exception as exc:
        logger.exception("shipment_apply_task failed job_id=%s — recording failure", job_id)
        from app.services.imports.shipment_apply_failure import record_shipment_apply_failure

        return record_shipment_apply_failure(job_id, exc)


def _shipment_bulk_progress(self, phase: str, phase_label: str):
    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "phase_label": phase_label,
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    return _on_progress


@celery_app.task(name="imports.shipment_bulk_map_customer", bind=True, ack_late=True)
def shipment_bulk_map_customer_task(self, job_id: int, payload: dict) -> dict:
    """Background bulk-map of shipment customer candidates to one customer (progress per candidate)."""
    from app.services.imports.shipment_bulk_steward_enqueue import run_shipment_bulk_map_customer_sync

    try:
        return run_shipment_bulk_map_customer_sync(
            job_id, payload, on_progress=_shipment_bulk_progress(self, "mapping_customers", "Mapping channel partners")
        )
    except Exception:
        logger.exception("shipment_bulk_map_customer failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.shipment_bulk_apply_plans", bind=True, ack_late=True)
def shipment_bulk_apply_plans_task(self, job_id: int, payload: dict) -> dict:
    """Background apply of persisted shipment candidate plans (progress per candidate)."""
    from app.services.imports.shipment_bulk_steward_enqueue import run_shipment_bulk_apply_plans_sync

    try:
        return run_shipment_bulk_apply_plans_sync(
            job_id, payload, on_progress=_shipment_bulk_progress(self, "applying_plans", "Applying confirmed plans")
        )
    except Exception:
        logger.exception("shipment_bulk_apply_plans failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.shipment_bulk_provisional_customers", bind=True, ack_late=True)
def shipment_bulk_provisional_customers_task(self, job_id: int, payload: dict) -> dict:
    """Background bulk provisional customer creation for shipment steward (progress per group)."""
    from app.services.imports.shipment_bulk_steward_enqueue import (
        run_shipment_bulk_provisional_customers_sync,
    )

    try:
        return run_shipment_bulk_provisional_customers_sync(
            job_id,
            payload,
            on_progress=_shipment_bulk_progress(self, "creating_provisional_customers", "Creating provisional customers"),
        )
    except Exception:
        logger.exception("shipment_bulk_provisional_customers failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.shipment_bulk_ignore", bind=True, ack_late=True)
def shipment_bulk_ignore_task(self, job_id: int, payload: dict) -> dict:
    """Batch reject shipment mapping candidates (steward_rejected per candidate commit)."""
    from app.services.imports.shipment_bulk_steward_enqueue import run_shipment_bulk_ignore_sync

    candidate_ids = payload.get("candidate_ids") or []

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "rejecting_candidates",
                    "phase_label": "Rejecting steward candidates",
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        return run_shipment_bulk_ignore_sync(
            job_id,
            payload,
            on_progress=_on_progress,
        )
    except Exception:
        logger.exception("shipment_bulk_ignore failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.shipment_resolution_plan_compute", bind=True, ack_late=True)
def shipment_resolution_plan_compute_task(self, job_id: int, payload: dict) -> dict:
    from app.services.imports.shipment_resolution_plan_compute_sync import run_shipment_resolution_plan_compute_sync

    try:
        return run_shipment_resolution_plan_compute_sync(
            job_id,
            payload,
            on_progress=_shipment_bulk_progress(self, "computing_plan", "Computing resolution plan"),
        )
    except Exception:
        logger.exception("shipment_resolution_plan_compute failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.shipment_resolution_plan_apply", bind=True, ack_late=True)
def shipment_resolution_plan_apply_task(self, job_id: int, payload: dict) -> dict:
    from app.services.imports.shipment_resolution_plan_apply_sync import run_shipment_resolution_plan_apply_sync

    try:
        return run_shipment_resolution_plan_apply_sync(
            job_id,
            payload,
            on_progress=_shipment_bulk_progress(self, "applying_plan", "Applying resolution plan"),
        )
    except Exception:
        logger.exception("shipment_resolution_plan_apply failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.cpor_historical_resolution_plan_compute", bind=True, ack_late=True)
def cpor_historical_resolution_plan_compute_task(self, job_id: int, payload: dict) -> dict:
    """Build the CPOR historical steward resolution plan off the HTTP request path (D-013)."""
    from app.services.cpor.historical_import.resolution_plan_enqueue import (
        run_cpor_historical_resolution_plan_compute_sync,
    )

    try:
        return run_cpor_historical_resolution_plan_compute_sync(
            job_id,
            payload,
            on_progress=_shipment_bulk_progress(self, "computing_plan", "Computing CPOR resolution plan"),
        )
    except Exception:
        logger.exception("cpor_historical_resolution_plan_compute failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.cpor_historical_resolution_plan_apply", bind=True, ack_late=True)
def cpor_historical_resolution_plan_apply_task(self, job_id: int, payload: dict) -> dict:
    """Apply CPOR historical resolution-plan rows — per-token map_staging_token calls (D-013)."""
    from app.services.cpor.historical_import.resolution_plan_enqueue import (
        run_cpor_historical_resolution_plan_apply_sync,
    )

    try:
        return run_cpor_historical_resolution_plan_apply_sync(
            job_id,
            payload,
            on_progress=_shipment_bulk_progress(self, "applying_plan", "Applying CPOR resolution plan"),
        )
    except Exception:
        logger.exception("cpor_historical_resolution_plan_apply failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.cpor_historical_apply", bind=True, ack_late=True)
def cpor_historical_apply_task(self, job_id: int) -> dict:
    """Background apply for ``cpor_historical_cases`` (staging → case/line upsert)."""
    from app.services.cpor.historical_import.apply_sync import run_cpor_historical_apply_sync

    def _on_progress(phase: str, phase_label: str, current_row: int, total_rows: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "phase_label": phase_label,
                    "current_row": current_row,
                    "total_rows": total_rows,
                    "pct": round(current_row / total_rows * 100) if total_rows else 0,
                },
            )
        except Exception:
            pass

    try:
        return run_cpor_historical_apply_sync(job_id, on_progress=_on_progress)
    except Exception:
        logger.exception("cpor_historical_apply_task failed job_id=%s", job_id)
        _write_task_level_failure(job_id)
        raise


@celery_app.task(name="imports.dsi_apply", bind=True, ack_late=True)
def dsi_apply_task(self, job_id: int) -> dict:
    """Background apply for a ``distributor_inventory`` job (pipeline apply → complete-to-loaded)."""
    from app.services.imports.dsi_apply_sync import run_dsi_apply_sync

    def _on_progress(phase: str, phase_label: str, current_row: int, total_rows: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": phase,
                    "phase_label": phase_label,
                    "current_row": current_row,
                    "total_rows": total_rows,
                    "pct": round(current_row / total_rows * 100) if total_rows else 0,
                },
            )
        except Exception:
            pass

    try:
        return run_dsi_apply_sync(job_id, on_progress=_on_progress)
    except Exception:
        logger.exception("dsi_apply_task failed job_id=%s — writing STAGE_FAILED", job_id)
        _write_task_level_failure(job_id)
        raise


@celery_app.task(name="imports.infer_dsi")
def infer_dsi_import_job_task(job_id: int) -> int:
    """DSI upload infer (headers + initial field_mapping → ``dsi_mapping_ready``)."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.dsi_mapping_workflow import infer_dsi_job_sync

    with SessionLocal() as db:
        infer_dsi_job_sync(db, job_id)
    return job_id


@celery_app.task(name="imports.dsi_bulk_ignore", bind=True, ack_late=True)
def dsi_bulk_ignore_task(self, job_id: int, payload: dict) -> dict:
    """Batch ignore DSI mapping candidates (single commit; one staging demotion pass)."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.dsi_bulk_ignore_sync import run_dsi_bulk_ignore_sync

    candidate_ids = payload.get("candidate_ids") or []
    notes = payload.get("notes")

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "ignoring_candidates",
                    "phase_label": "Ignoring steward candidates",
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        with SessionLocal() as db:
            return run_dsi_bulk_ignore_sync(
                db,
                job_id,
                list(candidate_ids),
                notes=notes,
                on_progress=_on_progress,
            )
    except Exception:
        logger.exception("dsi_bulk_ignore failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_bulk_provisional_customers", bind=True, ack_late=True)
def dsi_bulk_provisional_customers_task(self, job_id: int, payload: dict) -> dict:
    """Batch provisional customer creates for DSI bulk steward (single commit, one replan on client)."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.dsi_bulk_provisional_customers_sync import run_dsi_bulk_provisional_customers_sync

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "creating_provisional_customers",
                    "phase_label": "Creating provisional customers",
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        with SessionLocal() as db:
            result = run_dsi_bulk_provisional_customers_sync(
                db, job_id, payload, on_progress=_on_progress
            )
        from app.services.imports.dsi_post_validate_auto_apply import try_flush_deferred_dsi_post_validate_auto_apply

        with SessionLocal() as flush_db:
            if try_flush_deferred_dsi_post_validate_auto_apply(flush_db, job_id):
                flush_db.commit()
        return result
    except Exception:
        logger.exception("dsi_bulk_provisional_customers failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_resolution_plan_apply", bind=True, ack_late=True)
def dsi_resolution_plan_apply_task(self, job_id: int, payload: dict) -> dict:
    """Apply DSI resolution-plan rows (steward map/provisional/product) with progress updates."""
    from app.services.imports.dsi_post_validate_auto_apply import try_flush_deferred_dsi_post_validate_auto_apply
    from app.services.imports.dsi_resolution_plan_apply_sync import run_dsi_resolution_plan_apply_sync
    from app.db.session_sync import SessionLocal

    candidate_ids = payload.get("candidate_ids") or []
    total_rows = len(candidate_ids) if isinstance(candidate_ids, list) else 0

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "applying_resolution_plan",
                    "phase_label": "Applying resolution plan",
                    "current_row": current,
                    "total_rows": total or total_rows,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        _on_progress(0, total_rows or 1)
        result = run_dsi_resolution_plan_apply_sync(job_id, payload, on_progress=_on_progress)
        with SessionLocal() as db:
            if try_flush_deferred_dsi_post_validate_auto_apply(db, job_id):
                db.commit()
        return result
    except Exception:
        logger.exception("dsi_resolution_plan_apply failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_resolution_plan_compute", bind=True, ack_late=True)
def dsi_resolution_plan_compute_task(self, job_id: int, payload: dict) -> dict:
    """Build DSI steward resolution plan off the HTTP request path."""
    from app.services.imports.dsi_post_validate_auto_apply import try_flush_deferred_dsi_post_validate_auto_apply
    from app.services.imports.dsi_resolution_plan_compute_sync import run_dsi_resolution_plan_compute_sync
    from app.db.session_sync import SessionLocal

    def _on_progress(current: int, total: int) -> None:
        try:
            self.update_state(
                state="PROGRESS",
                meta={
                    "phase": "computing_resolution_plan",
                    "phase_label": "Computing resolution plan",
                    "current_row": current,
                    "total_rows": total,
                    "pct": round(current / total * 100) if total else 0,
                },
            )
        except Exception:
            pass

    try:
        result = run_dsi_resolution_plan_compute_sync(job_id, payload, on_progress=_on_progress)
        with SessionLocal() as db:
            if try_flush_deferred_dsi_post_validate_auto_apply(db, job_id):
                db.commit()
        return result
    except Exception:
        logger.exception("dsi_resolution_plan_compute failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_soh_reconciliation", bind=True, ack_late=True)
def dsi_soh_reconciliation_task(self, job_id: int, payload: dict) -> dict:
    """Background SOH reconciliation after DSI apply."""
    from app.services.imports.dsi_soh_reconciliation_sync import run_dsi_soh_reconciliation_sync

    try:
        return run_dsi_soh_reconciliation_sync(job_id, payload)
    except Exception:
        logger.exception("dsi_soh_reconciliation failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_velocity_compute", bind=True, ack_late=True)
def dsi_velocity_compute_task(self, job_id: int, payload: dict) -> dict:
    """Background sell-out velocity compute after DSI apply."""
    from app.services.imports.dsi_velocity_sync import run_dsi_velocity_compute_sync

    try:
        return run_dsi_velocity_compute_sync(job_id, payload)
    except Exception:
        logger.exception("dsi_velocity_compute failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.dsi_forecasting", bind=True, ack_late=True)
def dsi_forecasting_task(self, job_id: int, payload: dict) -> dict:
    """Background DSI forecasting after velocity compute."""
    from app.services.imports.dsi_forecasting_sync import run_dsi_forecasting_sync

    try:
        return run_dsi_forecasting_sync(job_id, payload)
    except Exception:
        logger.exception("dsi_forecasting failed job_id=%s", job_id)
        raise


@celery_app.task(name="customers.full_merge_confirm", bind=True, ack_late=True)
def customer_full_merge_confirm_task(self, payload: dict) -> dict:
    """Steward-confirmed full customer merge (name-similarity group)."""
    from app.db.session_sync import SessionLocal
    from app.services.customer_full_merge import confirm_customer_full_merge_sync

    with SessionLocal() as db:
        return confirm_customer_full_merge_sync(
            db,
            similarity_key=str(payload["similarity_key"]),
            survivor_id=int(payload["survivor_id"]),
            audit_note=str(payload["audit_note"]),
            performed_by=payload.get("performed_by"),
            customer_ids=payload.get("customer_ids"),
        )


@celery_app.task(name="distributors.full_merge_confirm", bind=True, ack_late=True)
def distributor_full_merge_confirm_task(self, payload: dict) -> dict:
    """Steward-confirmed full distributor merge (name-similarity group)."""
    from app.db.session_sync import SessionLocal
    from app.services.distributor_full_merge import confirm_distributor_full_merge_sync

    with SessionLocal() as db:
        return confirm_distributor_full_merge_sync(
            db,
            similarity_key=str(payload["similarity_key"]),
            survivor_id=int(payload["survivor_id"]),
            audit_note=str(payload["audit_note"]),
            performed_by=payload.get("performed_by"),
            distributor_ids=payload.get("distributor_ids"),
        )


@celery_app.task(name="customers.alias_scope_merge_confirm", bind=True, ack_late=True)
def customer_alias_scope_merge_confirm_task(self, payload: dict) -> dict:
    """Steward-confirmed customer alias-scope merge."""
    from app.db.session_sync import SessionLocal
    from app.services.customer_alias_scope_merge import confirm_customer_alias_scope_merge_sync

    with SessionLocal() as db:
        return confirm_customer_alias_scope_merge_sync(
            db,
            normalized_token=str(payload["normalized_token"]),
            source_definition_id=payload.get("source_definition_id"),
            distributor_id=payload.get("distributor_id"),
            survivor_id=int(payload["survivor_id"]),
            audit_note=str(payload["audit_note"]),
            performed_by=payload.get("performed_by"),
        )


def run_product_master_validate_job(job_id: int, *, celery_task_id: str | None) -> int:
    """Shared implementation for Celery worker and explicit dev-only dispatch paths."""
    from app.services.imports.pm_validate_sync import run_product_master_validate_sync

    if celery_task_id == "dev-in-process-thread":
        DEV_CELERY_LOGGER.warning(
            "EXECUTION: Product Master validate job_id=%s running in-process (DEV ONLY, "
            "CIP_DEV_CELERY_DISPATCH=in_process_thread). Not broker-isolated.",
            job_id,
        )

    try:
        return run_product_master_validate_sync(job_id, celery_task_id=celery_task_id)
    except Exception:
        logger.exception("product_master_validate job failed job_id=%s", job_id)
        raise


@celery_app.task(name="imports.product_master_validate", bind=True, ack_late=True)
def product_master_validate_task(self, job_id: int) -> int:
    """Background Product Master validation: must be enqueued via try_enqueue_pm_validate_sync first."""
    celery_id = getattr(getattr(self, "request", None), "id", None)
    return run_product_master_validate_job(
        job_id,
        celery_task_id=str(celery_id) if celery_id else None,
    )


@celery_app.task(name="commercial_planner.parse_lineup_case", bind=True, ack_late=True)
def commercial_planner_lineup_parse_task(
    self,
    case_id: int,
    filename: str,
    file_b64: str,
    import_job_id: int,
    template_slug: str = "current_lineup",
    source_code: str = "current_lineup_system",
) -> dict:
    """Background lineup parse for large uploads (current_lineup or unified_lineup)."""
    from app.services.commercial_planner.lineup_parse_worker import run_lineup_case_parse_job

    celery_id = getattr(getattr(self, "request", None), "id", None)
    if celery_id == "dev-in-process-thread":
        DEV_CELERY_LOGGER.warning(
            "EXECUTION: lineup parse case_id=%s in-process (DEV ONLY).",
            case_id,
        )
    try:
        return run_lineup_case_parse_job(
            case_id,
            filename,
            file_b64,
            import_job_id,
            celery_task_id=str(celery_id) if celery_id else None,
            template_slug=template_slug,
            source_code=source_code,
        )
    except Exception:
        logger.exception("lineup parse failed case_id=%s", case_id)
        raise


@celery_app.task(name="imports.product_master_commit", bind=True, ack_late=True)
def product_master_commit_task(self, job_id: int, confirm_destructive: bool) -> int:
    """Background Product Master apply: must be enqueued via try_enqueue_pm_commit_sync first."""
    celery_id = getattr(getattr(self, "request", None), "id", None)
    return run_product_master_commit_job(
        job_id,
        confirm_destructive,
        celery_task_id=str(celery_id) if celery_id else None,
    )


@celery_app.task(name="imports.reap_stale_running_jobs")
def reap_stale_running_jobs_task() -> dict:
    """Beat task: fail import jobs stuck ``running`` when Celery confirms work is dead."""
    from app.services.imports.running_import_job_reaper import reap_stale_running_import_jobs_sync
    from app.worker.celery_queues import dev_beat_disabled

    if dev_beat_disabled():
        return {"skipped": True, "reason": "dev_beat_disabled"}

    return reap_stale_running_import_jobs_sync()


@celery_app.task(name="imports.cst_advance_report_slots")
def cst_advance_report_slots_task() -> dict:
    """Beat task: create/advance CST expected-report slots (due→late→missing). Idempotent."""
    from app.db.session_sync import SessionLocal
    from app.services.imports.cst_d1 import advance_cst_report_slots
    from app.worker.celery_queues import dev_beat_disabled

    if dev_beat_disabled():
        return {"skipped": True, "reason": "dev_beat_disabled"}

    with SessionLocal() as session:
        result = advance_cst_report_slots(session)
        session.commit()
        return result


@celery_app.task(name="listing_capture.poll_listings")
def listing_capture_poll_listings_task() -> dict:
    """Beat task: gated no-op unless schedule enabled and listings exist. No live HTTP in LC-U1."""
    from app.db.session_sync import SessionLocal
    from app.services.listing_capture.registry import scheduler_should_run
    from app.worker.celery_queues import dev_beat_disabled

    if dev_beat_disabled():
        return {"skipped": True, "reason": "dev_beat_disabled"}

    with SessionLocal() as session:
        gate = scheduler_should_run(session)
        if not gate["should_run"]:
            return {"skipped": True, "reason": "schedule_disabled_or_empty", **gate}
        # Live fetch intentionally not wired — Warren enables schedule + injects fetcher later.
        return {"skipped": True, "reason": "live_fetch_not_enabled_in_lc_u1", **gate}


@celery_app.task(name="imports.flush_deferred_dsi_post_validate_auto_apply")
def flush_deferred_dsi_post_validate_auto_apply_task(job_id: int) -> dict:
    """Batch-queue task: enqueue deferred historical auto-apply when steward is idle."""
    from app.services.imports.dsi_post_validate_auto_apply import (
        run_flush_deferred_dsi_post_validate_auto_apply_sync,
    )

    return run_flush_deferred_dsi_post_validate_auto_apply_sync(job_id)
