"""Unit tests for the async shipment bulk steward path (no database I/O).

Covers Unit 1 behavior:
  * ``enqueue_shipment_bulk_task`` dispatches to the broker first (async_poll=True), falls back to a
    dev in-process thread, then to inline sync — never silently for normal broker operation.
  * The three bulk ``execute_*`` functions accept and invoke ``on_progress`` so the worker can stream
    progress.
  * The ``shipment_bulk_task`` slot is registered and cleared by ``clear_all_task_slots`` (orphan-slot
    fix: cancel/retry can no longer leave a dangling shipment bulk slot).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.services.imports.shipment_bulk_steward_enqueue as enq
import app.services.imports.shipment_evidence_steward_ops as ops
from app.services.imports.import_background_slots import (
    SLOT_SHIPMENT_BULK,
    clear_all_task_slots,
    has_any_task_slot,
    iter_active_slots,
    set_task_slot_on_job,
    slot_meta_keys,
)


# --- enqueue dispatch paths -----------------------------------------------------


def test_enqueue_uses_broker_first(monkeypatch) -> None:
    sent = {}

    def _fake_send_task(name, args=None, **kw):
        sent["name"] = name
        sent["args"] = args
        return SimpleNamespace(id="broker-task-123")

    monkeypatch.setattr(enq.celery_app, "send_task", _fake_send_task)

    ran_sync = {"called": False}

    def _run_sync():
        ran_sync["called"] = True
        return {"ok": True}

    task_id, async_poll = enq.enqueue_shipment_bulk_task(
        task_name=enq.TASK_SHIPMENT_BULK_MAP_CUSTOMER,
        job_id=7,
        payload={"candidate_ids": [1], "customer_id": 2},
        run_sync=_run_sync,
        dev_prefix="ship-bulk-map",
    )

    assert task_id == "broker-task-123"
    assert async_poll is True
    assert sent["name"] == enq.TASK_SHIPMENT_BULK_MAP_CUSTOMER
    assert sent["args"] == [7, {"candidate_ids": [1], "customer_id": 2}]
    # Broker accepted: the inline sync path must NOT run.
    assert ran_sync["called"] is False


def test_enqueue_dev_thread_fallback_on_broker_failure(monkeypatch) -> None:
    def _boom(*a, **k):
        raise RuntimeError("broker down")

    monkeypatch.setattr(enq.celery_app, "send_task", _boom)
    monkeypatch.setattr(enq, "get_settings", lambda: SimpleNamespace(cip_dev_celery_dispatch="in_process_thread"))

    task_id, async_poll = enq.enqueue_shipment_bulk_task(
        task_name=enq.TASK_SHIPMENT_BULK_APPLY_PLANS,
        job_id=9,
        payload={"candidate_ids": [1, 2]},
        run_sync=lambda: {"applied": [1, 2], "errors": []},
        dev_prefix="ship-bulk-plans",
    )

    assert async_poll is True  # still pollable
    assert task_id.startswith("dev-ship-bulk-plans-")
    # Thread runs run_sync and stashes the result in the dev store.
    deadline = time.time() + 5
    store = enq.dev_shipment_bulk_task_results()
    while time.time() < deadline and task_id not in store:
        time.sleep(0.02)
    assert store.get(task_id, {}).get("state") == "SUCCESS"
    assert store[task_id]["result"] == {"applied": [1, 2], "errors": []}


def test_enqueue_sync_fallback_when_no_dev_thread(monkeypatch) -> None:
    def _boom(*a, **k):
        raise RuntimeError("broker down")

    monkeypatch.setattr(enq.celery_app, "send_task", _boom)
    monkeypatch.setattr(enq, "get_settings", lambda: SimpleNamespace(cip_dev_celery_dispatch="broker"))

    task_id, async_poll = enq.enqueue_shipment_bulk_task(
        task_name=enq.TASK_SHIPMENT_BULK_PROVISIONAL_CUSTOMERS,
        job_id=4,
        payload={"candidate_ids": [5]},
        run_sync=lambda: {"ok": True, "results": [], "errors": []},
        dev_prefix="ship-bulk-prov",
    )

    assert async_poll is False  # ran inline; client should not poll
    assert task_id.startswith("sync-ship-bulk-prov-")
    assert enq.dev_shipment_bulk_task_results()[task_id]["result"]["ok"] is True


# --- on_progress passthrough ----------------------------------------------------


def _fake_db_no_candidates() -> MagicMock:
    db = MagicMock()
    db.get.return_value = None  # every candidate "not found" -> still iterates + emits progress
    return db


def test_bulk_map_customer_emits_progress() -> None:
    db = _fake_db_no_candidates()
    seen: list[tuple[int, int]] = []
    out = ops.execute_bulk_map_shipment_customers(
        db, customer_id=1, candidate_ids=[10, 11, 12], on_progress=lambda c, t: seen.append((c, t))
    )
    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert out["mapped"] == []  # none resolved (all "not found")


def test_bulk_apply_plans_emits_progress() -> None:
    db = _fake_db_no_candidates()
    seen: list[tuple[int, int]] = []
    ops.execute_bulk_apply_shipment_candidate_plans(
        db, import_job_id=5, candidate_ids=[1, 2], on_progress=lambda c, t: seen.append((c, t))
    )
    assert seen == [(1, 2), (2, 2)]


# --- slot register + clear (orphan-slot fix) ------------------------------------


def test_shipment_bulk_slot_registered_and_cleared() -> None:
    assert "shipment_bulk_task" in slot_meta_keys()

    job = SimpleNamespace(id=42, template_slug="inbound_shipments", import_mode="apply", staged_metadata=None)
    set_task_slot_on_job(job, SLOT_SHIPMENT_BULK, task_id="t-1", label="Mapping channel partners…")
    assert has_any_task_slot(job.staged_metadata)
    active = list(iter_active_slots(job))
    assert any(s.slot_key == SLOT_SHIPMENT_BULK and s.task_id == "t-1" for s in active)

    cleared = clear_all_task_slots(job.staged_metadata)
    assert cleared is None or "shipment_bulk_task" not in cleared
