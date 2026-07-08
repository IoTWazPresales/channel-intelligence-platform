"""Synchronous worker for applying an ``inbound_shipments`` import job.

Backgrounded counterpart to the old in-request apply path. Runs the same three steps the
endpoint used to run inline — auto-map high-confidence planner candidates, upsert
``fact_inbound_shipment`` (batched), advance the job to ``loaded`` — but as a Celery task
(or dev in-process thread) with progress callbacks, so the HTTP request returns immediately
instead of holding a connection open for ~5 minutes on large jobs.

This is the apply piece of the shipment pipeline's consistent background + batched + progress
shape (validate and bulk steward already have it).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import STAGE_LOADED
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.import_job_background_metadata import (
    persist_clear_background_task_metadata,
    persist_pipeline_worker_started_at,
)
from app.services.imports.shipment_apply_failure import record_shipment_apply_failure
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
    enrich_shipment_customer_token_candidates,
    enrich_shipment_distributor_candidates,
)
from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    _apply_map_shipment_customer_without_commit,
    _apply_map_shipment_distributor_without_commit,
)
from app.services.imports.shipment_inbound_facts import upsert_inbound_shipment_facts_for_job

# Progress callback: (phase, phase_label, current_row, total_rows). Mirrors the meta shape the
# Celery PROGRESS reader (`/imports/jobs/{job_id}/dsi-progress`) and the global background-task
# indicator already understand.
ProgressFn = Callable[[str, str, int, int], None]

logger = logging.getLogger(__name__)


def _shipment_candidate_eligible_for_apply_auto_map(cand: ImportEntityMappingCandidate) -> bool:
    """Align with ``shipment_evidence_resolution_plan`` scoring for map paths.

    ``map_distributor`` / ``map_customer`` are only emitted with ``confidence_score`` of **1.0** or **0.95**;
    all other actions use lower scores. Require ``needs_review``, ``suggested_entity_id``, and entity/action match.
    """
    if cand.status != "needs_review":
        return False
    sc = cand.confidence_score
    if sc is None:
        return False
    try:
        score = float(sc)
    except (TypeError, ValueError):
        return False
    if score < 0.95:
        return False
    ctx = cand.context if isinstance(cand.context, dict) else {}
    action = (str(ctx.get("suggested_action") or "")).strip()
    if cand.suggested_entity_id is None:
        return False
    if action == "map_distributor":
        return cand.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY
    if action == "map_customer":
        return cand.entity_type == SHIPMENT_CUSTOMER_ENTITY
    return False


def apply_high_confidence_shipment_mapping_candidates(import_job_id: int) -> int:
    """Map high-confidence planner suggestions; enrich and commit once per entity type (not per candidate)."""
    applied: list[int] = []
    any_customer = False
    any_distributor = False
    with SessionLocal() as s:
        ids = [
            int(x)
            for x in s.scalars(
                select(ImportEntityMappingCandidate.id).where(
                    ImportEntityMappingCandidate.import_job_id == int(import_job_id),
                    ImportEntityMappingCandidate.entity_type.in_(
                        (SHIPMENT_DISTRIBUTOR_ENTITY, SHIPMENT_CUSTOMER_ENTITY)
                    ),
                    ImportEntityMappingCandidate.status == "needs_review",
                ).order_by(ImportEntityMappingCandidate.id)
            ).all()
        ]
        for cid in ids:
            cand = s.get(ImportEntityMappingCandidate, cid)
            if cand is None or not _shipment_candidate_eligible_for_apply_auto_map(cand):
                continue
            ctx = cand.context if isinstance(cand.context, dict) else {}
            action = (str(ctx.get("suggested_action") or "")).strip()
            eid = int(cand.suggested_entity_id)
            try:
                if action == "map_distributor":
                    _apply_map_shipment_distributor_without_commit(
                        s, cand, distributor_id=eid, raw_token=None
                    )
                    any_distributor = True
                    applied.append(cid)
                elif action == "map_customer":
                    _apply_map_shipment_customer_without_commit(
                        s, cand, customer_id=eid, raw_token=None
                    )
                    any_customer = True
                    applied.append(cid)
            except ShipmentStewardOpError:
                continue
        if applied:
            sid: int | None = None
            for cid in reversed(applied):
                c = s.get(ImportEntityMappingCandidate, cid)
                if c is not None:
                    sid = int(c.source_definition_id) if c.source_definition_id is not None else None
                    break
            if any_customer:
                enrich_shipment_customer_token_candidates(
                    s, import_job_id=int(import_job_id), source_definition_id=sid
                )
                s.commit()
            if any_distributor:
                enrich_shipment_distributor_candidates(
                    s, import_job_id=int(import_job_id), source_definition_id=sid
                )
                s.commit()
    return len(applied)


def run_shipment_apply_sync(
    db: Session,
    job_id: int,
    *,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Apply an ``inbound_shipments`` job: auto-map candidates → upsert facts (batched) → ``loaded``.

    Idempotent and safe to re-run: the auto-map step only touches ``needs_review`` candidates and
    the fact upsert is keyed on ``source_key`` (latest-job-wins). Returns a small summary used by
    the synchronous fallback path; the Celery/thread path discards it.
    """

    def _emit(phase: str, label: str, current: int, total: int) -> None:
        if on_progress is not None:
            try:
                on_progress(phase, label, current, total)
            except Exception:
                pass

    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != "inbound_shipments":
        return {"id": job_id, "outcome": "not_found"}

    persist_pipeline_worker_started_at(db, job)
    db.commit()

    _emit("applying_mappings", "Applying high-confidence mappings", 0, 0)
    auto_applied = apply_high_confidence_shipment_mapping_candidates(job_id)

    def _facts_progress(current: int, total: int) -> None:
        _emit("writing_facts", "Writing shipment facts", current, total)

    _emit("writing_facts", "Writing shipment facts", 0, 0)
    try:
        fact_rows = upsert_inbound_shipment_facts_for_job(db, job_id, on_progress=_facts_progress)
        db.commit()
    except Exception as exc:
        logger.exception("run_shipment_apply_sync fact upsert failed job_id=%s", job_id)
        try:
            db.rollback()
        except Exception:
            pass
        return record_shipment_apply_failure(job_id, exc)

    unresolved_product_rows = int(
        db.scalar(
            select(func.count())
            .select_from(ShipmentEvidenceLine)
            .where(
                ShipmentEvidenceLine.import_job_id == int(job_id),
                ShipmentEvidenceLine.product_id.is_(None),
            )
        )
        or 0
    )

    job = db.get(ImportJob, job_id)
    if job is not None:
        job.stage = STAGE_LOADED
        # Mirror DSI apply completion: successful fact upsert → completed + loaded.
        # Unresolved products are non-blocking write-through (validate blocking==0 path);
        # see complete_dsi_import_job_to_loaded (status=completed when facts upsert OK).
        job.status = "completed"
        job.error_summary = None
        job.completed_at = datetime.now(timezone.utc)
        persist_clear_background_task_metadata(db, job)
        db.commit()

    _emit("complete", "Apply complete", fact_rows, fact_rows)
    return {
        "id": job_id,
        "outcome": "applied",
        "auto_applied_candidate_count": auto_applied,
        "fact_rows": fact_rows,
        "unresolved_product_rows": unresolved_product_rows,
    }
