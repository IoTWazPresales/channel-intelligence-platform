"""Dual-write task_run ledger — populate only; readers unchanged."""

from __future__ import annotations

import contextvars
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, TypeVar

from sqlalchemy.exc import IntegrityError

from app.models.task_run import TaskRun

logger = logging.getLogger(__name__)

T = TypeVar("T")

ENTITY_IMPORT_JOB = "import_job"
ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE = "customer_alias_scope_merge"
ENTITY_CUSTOMER_FULL_MERGE = "customer_full_merge"
ENTITY_DISTRIBUTOR_FULL_MERGE = "distributor_full_merge"

TRANSPORT_BROKER = "broker"
TRANSPORT_IN_PROCESS_THREAD = "in_process_thread"
TRANSPORT_INLINE_SYNC = "inline_sync"

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"

# Celery-compatible states for HTTP poll consumers.
POLL_STATE_PENDING = "PENDING"
POLL_STATE_STARTED = "STARTED"
POLL_STATE_SUCCESS = "SUCCESS"
POLL_STATE_FAILURE = "FAILURE"

TASK_CLASS_BY_NAME: dict[str, str] = {
    "imports.process_job": "pipeline",
    "imports.infer_dsi": "pipeline",
    "imports.dsi_apply": "pipeline",
    "imports.shipment_apply": "pipeline",
    "imports.product_master_validate": "master",
    "imports.product_master_commit": "master",
    "imports.dsi_bulk_provisional_customers": "steward",
    "imports.dsi_bulk_ignore": "steward",
    "imports.dsi_resolution_plan_apply": "steward",
    "imports.dsi_resolution_plan_compute": "steward",
    "imports.shipment_bulk_map_customer": "steward",
    "imports.shipment_bulk_apply_plans": "steward",
    "imports.shipment_bulk_provisional_customers": "steward",
    "imports.shipment_bulk_ignore": "steward",
    "imports.shipment_resolution_plan_compute": "steward",
    "imports.shipment_resolution_plan_apply": "steward",
    "imports.cpor_historical_resolution_plan_compute": "steward",
    "imports.cpor_historical_resolution_plan_apply": "steward",
    "imports.cst_resolution_plan_compute": "steward",
    "imports.cst_resolution_plan_apply": "steward",
    "imports.cst_bulk_ignore": "steward",
    "imports.dsi_soh_reconciliation": "derive",
    "imports.dsi_velocity_compute": "derive",
    "imports.dsi_forecasting": "derive",
    "customers.alias_scope_merge_confirm": "master",
    "customers.full_merge_confirm": "master",
    "distributors.full_merge_confirm": "master",
    "commercial_planner.parse_lineup_case": "lineup",
}

_current_task_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_task_run_id",
    default=None,
)


def task_class_for(task_name: str) -> str:
    return TASK_CLASS_BY_NAME.get(task_name, "background")


def mint_synthetic_task_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def task_run_poll_state(ledger_state: str | None) -> str:
    """Map ``task_run.state`` to Celery-style poll states for API consumers."""
    key = (ledger_state or "").strip().lower()
    if key == STATE_SUCCEEDED:
        return POLL_STATE_SUCCESS
    if key == STATE_FAILED:
        return POLL_STATE_FAILURE
    if key == STATE_RUNNING:
        return POLL_STATE_STARTED
    return POLL_STATE_PENDING


def read_task_run_poll_progress_sync(task_run_id: str) -> dict[str, Any] | None:
    """Read poll payload from ``task_run`` (canonical when Celery uses ``ignore_result=True``)."""
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        row = db.get(TaskRun, task_run_id)
        if row is None:
            return None
        poll_state = task_run_poll_state(row.state)
        progress: dict[str, Any] = {"task_id": task_run_id, "state": poll_state}
        if poll_state == POLL_STATE_FAILURE:
            progress["error"] = (row.error_summary or "Task failed")[:800]
        return progress


def entity_from_task_args(task_name: str, args: tuple[Any, ...]) -> tuple[str, int]:
    if task_name == "commercial_planner.parse_lineup_case":
        if len(args) > 3:
            return ENTITY_IMPORT_JOB, int(args[3])
        if args:
            return ENTITY_IMPORT_JOB, int(args[0])
        return ENTITY_IMPORT_JOB, 0
    if task_name == "customers.alias_scope_merge_confirm":
        if args and isinstance(args[0], dict):
            payload = args[0]
            try:
                survivor_id = int(payload.get("survivor_id") or 0)
            except (TypeError, ValueError):
                survivor_id = 0
            return ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE, survivor_id
        return ENTITY_CUSTOMER_ALIAS_SCOPE_MERGE, 0
    if task_name == "customers.full_merge_confirm":
        if args and isinstance(args[0], dict):
            payload = args[0]
            try:
                survivor_id = int(payload.get("survivor_id") or 0)
            except (TypeError, ValueError):
                survivor_id = 0
            return ENTITY_CUSTOMER_FULL_MERGE, survivor_id
        return ENTITY_CUSTOMER_FULL_MERGE, 0
    if task_name == "distributors.full_merge_confirm":
        if args and isinstance(args[0], dict):
            payload = args[0]
            try:
                survivor_id = int(payload.get("survivor_id") or 0)
            except (TypeError, ValueError):
                survivor_id = 0
            return ENTITY_DISTRIBUTOR_FULL_MERGE, survivor_id
        return ENTITY_DISTRIBUTOR_FULL_MERGE, 0
    if args:
        return ENTITY_IMPORT_JOB, int(args[0])
    return ENTITY_IMPORT_JOB, 0


def set_current_task_run_id(task_run_id: str | None) -> contextvars.Token[str | None]:
    return _current_task_run_id.set(task_run_id)


def reset_current_task_run_id(token: contextvars.Token[str | None]) -> None:
    _current_task_run_id.reset(token)


def current_task_run_id() -> str | None:
    return _current_task_run_id.get()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _promote_task_run_to_running(row: TaskRun, now: datetime) -> None:
    if row.state in (STATE_SUCCEEDED, STATE_FAILED):
        return
    row.state = STATE_RUNNING
    if row.started_at is None:
        row.started_at = now


def _fresh_session_commit(fn: Callable[[Any], None]) -> None:
    from app.db.session_sync import SessionLocal

    try:
        with SessionLocal() as db:
            fn(db)
            db.commit()
    except Exception:
        logger.exception("task_run ledger write failed")


def create_queued_task_run(
    *,
    task_run_id: str,
    task_name: str,
    entity_type: str,
    entity_id: int,
    transport: str,
) -> None:
    """Insert a queued row in its own short transaction (best-effort)."""

    def _write(db) -> None:
        if db.get(TaskRun, task_run_id) is not None:
            return
        row = TaskRun(
            id=task_run_id,
            task_name=task_name,
            task_class=task_class_for(task_name),
            transport=transport,
            entity_type=entity_type,
            entity_id=int(entity_id),
            state=STATE_QUEUED,
        )
        db.add(row)
        try:
            # Plain flush (not begin_nested): nested savepoints still flush the outer
            # transaction first, so a UniqueViolation leaves PendingRollbackError and the
            # recovery get() fails. Fresh-session writers can rollback the whole unit.
            db.flush()
        except IntegrityError:
            db.rollback()
            return

    _fresh_session_commit(_write)


def ensure_task_run_running(
    task_run_id: str,
    *,
    task_name: str,
    entity_type: str,
    entity_id: int,
    transport: str = TRANSPORT_BROKER,
) -> None:
    """Mark running; create row if worker started without a dispatch write."""

    now = _now()

    def _write(db) -> None:
        row = db.get(TaskRun, task_run_id)
        if row is not None:
            _promote_task_run_to_running(row, now)
            db.add(row)
            return
        row = TaskRun(
            id=task_run_id,
            task_name=task_name,
            task_class=task_class_for(task_name),
            transport=transport,
            entity_type=entity_type,
            entity_id=int(entity_id),
            state=STATE_RUNNING,
            started_at=now,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            # Race with create_queued_task_run on fast broker pickup — promote existing row.
            db.rollback()
            existing = db.get(TaskRun, task_run_id)
            if existing is None:
                raise
            _promote_task_run_to_running(existing, now)
            db.add(existing)

    _fresh_session_commit(_write)


def mark_task_run_running(task_run_id: str) -> None:
    now = _now()

    def _write(db) -> None:
        row = db.get(TaskRun, task_run_id)
        if row is None or row.state in (STATE_SUCCEEDED, STATE_FAILED):
            return
        row.state = STATE_RUNNING
        if row.started_at is None:
            row.started_at = now
        db.add(row)

    _fresh_session_commit(_write)


def mark_task_run_succeeded(task_run_id: str) -> None:
    now = _now()

    def _write(db) -> None:
        row = db.get(TaskRun, task_run_id)
        if row is None or row.state in (STATE_SUCCEEDED, STATE_FAILED):
            return
        row.state = STATE_SUCCEEDED
        row.finished_at = now
        row.error_summary = None
        db.add(row)

    _fresh_session_commit(_write)


def mark_task_run_failed(task_run_id: str, error_summary: str | None = None) -> None:
    now = _now()
    summary = (error_summary or "Task failed")[:2000]

    def _write(db) -> None:
        row = db.get(TaskRun, task_run_id)
        if row is None:
            return
        if row.state == STATE_SUCCEEDED:
            return
        row.state = STATE_FAILED
        row.finished_at = now
        row.error_summary = summary
        db.add(row)

    _fresh_session_commit(_write)


def heartbeat_task_run(task_run_id: str) -> None:
    """Side-channel heartbeat bump (fresh session, independent transaction)."""
    now = _now()

    def _write(db) -> None:
        row = db.get(TaskRun, task_run_id)
        if row is None or row.state in (STATE_SUCCEEDED, STATE_FAILED):
            return
        row.heartbeat_at = now
        db.add(row)

    _fresh_session_commit(_write)


def heartbeat_current_task_run() -> None:
    task_run_id = current_task_run_id()
    if task_run_id:
        heartbeat_task_run(task_run_id)


@contextmanager
def task_run_execution(task_run_id: str) -> Iterator[None]:
    """Wrap in-process-thread and inline-sync execution paths."""
    token = set_current_task_run_id(task_run_id)
    try:
        mark_task_run_running(task_run_id)
        yield
        mark_task_run_succeeded(task_run_id)
    except Exception as exc:
        mark_task_run_failed(task_run_id, str(exc))
        raise
    finally:
        reset_current_task_run_id(token)


def spawn_in_process_thread_with_ledger(
    *,
    task_run_id: str,
    thread_name: str,
    target: Callable[[], None],
) -> None:
    import threading

    def _wrapped() -> None:
        with task_run_execution(task_run_id):
            target()

    threading.Thread(target=_wrapped, name=thread_name, daemon=True).start()


def run_inline_with_ledger(task_run_id: str, fn: Callable[[], T]) -> T:
    with task_run_execution(task_run_id):
        return fn()
