"""Registry-driven background-task slot writer/reader/clearer (Phase 2)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.import_background_slots import (
    KIND_DSI_BULK_PROVISIONAL,
    KIND_DSI_PIPELINE,
    KIND_DSI_RESOLUTION_PLAN_APPLY,
    KIND_PRODUCT_MASTER_COMMIT,
    KIND_SHIPMENT_IMPORT,
    SLOT_DSI_BULK,
    SLOT_DSI_SOH,
    SLOT_MAIN,
    SLOT_PM_COMMIT,
    clear_all_task_slots,
    clear_task_slot_on_job,
    iter_active_slots,
    set_task_slot_by_job_id,
    set_task_slot_on_job,
    slot_meta_keys,
)


def _job(**kw):
    base = {
        "id": 7,
        "template_slug": "distributor_inventory",
        "import_mode": "validate",
        "staged_metadata": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_fixed_slot_round_trip() -> None:
    job = _job(template_slug="product_master", import_mode="apply")
    set_task_slot_on_job(job, SLOT_PM_COMMIT, task_id="commit-1", async_poll=True)

    payload = job.staged_metadata["pm_commit_task"]
    assert payload["task_id"] == "commit-1"
    assert payload["kind"] == KIND_PRODUCT_MASTER_COMMIT
    assert payload["label"] == "Committing product master…"
    assert payload["async_poll"] is True
    assert "queued_at" in payload

    slots = list(iter_active_slots(job))
    assert len(slots) == 1
    assert slots[0].slot_key == SLOT_PM_COMMIT
    assert slots[0].kind == KIND_PRODUCT_MASTER_COMMIT
    assert slots[0].task_id == "commit-1"

    clear_task_slot_on_job(job, SLOT_PM_COMMIT)
    assert job.staged_metadata is None
    assert list(iter_active_slots(job)) == []


def test_main_slot_is_bare_string_and_kind_from_template_slug() -> None:
    dsi = _job(template_slug="distributor_inventory", import_mode="validate")
    set_task_slot_on_job(dsi, SLOT_MAIN, task_id="main-1")
    assert dsi.staged_metadata["celery_task_id"] == "main-1"  # bare string, not dict
    (slot,) = list(iter_active_slots(dsi))
    assert slot.kind == KIND_DSI_PIPELINE
    assert slot.label == "Validating DSI import 7"

    ship = _job(template_slug="inbound_shipments", import_mode="validate")
    set_task_slot_on_job(ship, SLOT_MAIN, task_id="ship-1")
    (slot,) = list(iter_active_slots(ship))
    assert slot.kind == KIND_SHIPMENT_IMPORT

    pm = _job(template_slug="product_master", import_mode="apply")
    set_task_slot_on_job(pm, SLOT_MAIN, task_id="pm-1")
    (slot,) = list(iter_active_slots(pm))
    assert slot.kind == KIND_PRODUCT_MASTER_COMMIT


def test_dsi_bulk_kind_from_payload_and_legacy_normalization() -> None:
    plan = _job()
    set_task_slot_on_job(plan, SLOT_DSI_BULK, task_id="plan-1", kind=KIND_DSI_RESOLUTION_PLAN_APPLY, candidate_count=3)
    payload = plan.staged_metadata["dsi_bulk_task"]
    assert payload["kind"] == KIND_DSI_RESOLUTION_PLAN_APPLY
    assert payload["candidate_count"] == 3
    (slot,) = list(iter_active_slots(plan))
    assert slot.kind == KIND_DSI_RESOLUTION_PLAN_APPLY
    assert slot.label == "Applying resolution plan (DSI job 7)"

    # Legacy kind string normalizes to dsi_bulk_provisional on read.
    legacy = _job()
    set_task_slot_on_job(legacy, SLOT_DSI_BULK, task_id="prov-1", kind="dsi_bulk_provisional_customers")
    (slot,) = list(iter_active_slots(legacy))
    assert slot.kind == KIND_DSI_BULK_PROVISIONAL


def test_soh_slot_byte_compatible_payload() -> None:
    job = _job()
    set_task_slot_on_job(job, SLOT_DSI_SOH, task_id="soh-1", async_poll=True)
    payload = job.staged_metadata["dsi_soh_reconcile_task"]
    assert set(payload.keys()) == {"task_id", "async_poll", "kind", "label", "queued_at"}
    assert payload["kind"] == "dsi_soh_reconciliation"
    assert payload["label"] == "Reconciling inventory…"


def test_clear_all_task_slots_strips_every_slot_and_timing() -> None:
    meta = {
        "celery_task_id": "abc",
        "dsi_bulk_task": {"task_id": "x"},
        "dsi_soh_reconcile_task": {"task_id": "s"},
        "dsi_velocity_compute_task": {"task_id": "v"},
        "dsi_forecasting_task": {"task_id": "f"},
        "pm_validate_task": {"task_id": "pv"},
        "pm_commit_task": {"task_id": "pc"},
        "lineup_parse_task": {"task_id": "lp"},
        "pipeline_queued_at": "2026-01-01T00:00:00+00:00",
        "pipeline_started_at": "2026-01-01T00:00:01+00:00",
        "dsi_validate_total_rows": 10,
    }
    cleared = clear_all_task_slots(meta)
    assert cleared == {"dsi_validate_total_rows": 10}


def test_set_task_slot_by_job_id_uses_session(monkeypatch) -> None:
    captured = {}

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, _model, jid):
            captured["jid"] = jid
            return _job(template_slug="product_master", import_mode="apply")

        def add(self, job):
            captured["job"] = job

        def commit(self):
            captured["committed"] = True

    monkeypatch.setattr("app.db.session_sync.SessionLocal", lambda: _FakeSession())
    set_task_slot_by_job_id(11, SLOT_PM_COMMIT, task_id="c-1")
    assert captured["jid"] == 11
    assert captured["committed"] is True
    assert captured["job"].staged_metadata["pm_commit_task"]["task_id"] == "c-1"


def test_slot_meta_keys_cover_all_known_slots() -> None:
    keys = set(slot_meta_keys())
    assert keys == {
        "celery_task_id",
        "dsi_bulk_task",
        "dsi_soh_reconcile_task",
        "dsi_velocity_compute_task",
        "dsi_forecasting_task",
        "pm_validate_task",
        "pm_commit_task",
        "lineup_parse_task",
    }
