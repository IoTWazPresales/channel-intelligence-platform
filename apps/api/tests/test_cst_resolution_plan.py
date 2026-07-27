"""Unit E2 — CST resolution-plan engine (mirror D-013)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.imports.cst_mapping_candidates import CST_LOCATION_ENTITY, CST_PRODUCT_ENTITY
from app.services.imports.cst_resolution_plan import build_cst_resolution_plan_sync
from app.services.imports.cst_resolution_plan_apply_sync import (
    run_cst_resolution_plan_apply_orchestrator,
)
from app.services.imports.cst_resolution_plan_enqueue import (
    TASK_CST_RESOLUTION_PLAN_APPLY,
    TASK_CST_RESOLUTION_PLAN_COMPUTE,
)
from app.services.imports.import_background_slots import (
    SLOT_CST_RESOLUTION_PLAN,
    SLOT_MAIN,
    clear_task_slot_on_job,
    set_task_slot_on_job,
    slot_meta_keys,
)


def _cand(
    *,
    id: int,
    entity_type: str,
    key: str,
    status: str = "needs_review",
    suggestions: list | None = None,
    confidence: float | None = None,
    match_reason: str | None = None,
    row_count: int = 1,
):
    return SimpleNamespace(
        id=id,
        import_job_id=1,
        entity_type=entity_type,
        normalized_key=key,
        row_count=row_count,
        total_units=None,
        total_reported_value=None,
        sample_raw_values=[key],
        suggested_entity_id=(suggestions[0]["dim_id"] if suggestions else None),
        match_reason=match_reason,
        confidence_score=confidence,
        status=status,
        context={"suggestions": suggestions or []},
        created_at=None,
        updated_at=None,
    )


def test_build_plan_ready_single_high_suggestion(monkeypatch):
    job = SimpleNamespace(id=1, template_slug="customer_sell_through")
    db = MagicMock()
    db.get.return_value = job
    rows = [
        _cand(
            id=10,
            entity_type=CST_PRODUCT_ENTITY,
            key="sku-a",
            suggestions=[{"dim_id": 5, "label": "A", "score": 1.0, "reason": "item_code"}],
            confidence=1.0,
            match_reason="item_code",
        )
    ]
    sm = MagicMock()
    sm.all.return_value = rows
    db.scalars.return_value = sm

    out = build_cst_resolution_plan_sync(db, 1)
    assert out["summary"]["ready"] == 1
    assert out["rows"][0]["ready"] is True
    assert out["rows"][0]["suggested_target_id"] == 5
    assert out["rows"][0]["suggested_action"] == "map_product"


def test_build_plan_collision_not_ready(monkeypatch):
    job = SimpleNamespace(id=1, template_slug="customer_sell_through")
    db = MagicMock()
    db.get.return_value = job
    rows = [
        _cand(
            id=11,
            entity_type=CST_PRODUCT_ENTITY,
            key="amb",
            suggestions=[
                {"dim_id": 1, "label": "A", "score": 1.0, "reason": "exact_key_collision:ean"},
                {"dim_id": 2, "label": "B", "score": 1.0, "reason": "exact_key_collision:ean"},
            ],
            confidence=1.0,
        )
    ]
    sm = MagicMock()
    sm.all.return_value = rows
    db.scalars.return_value = sm

    out = build_cst_resolution_plan_sync(db, 1)
    assert out["summary"]["ready"] == 0
    assert out["rows"][0]["ready"] is False
    assert out["rows"][0]["plan_class"] == "needs_review"


def test_apply_uses_per_candidate_target(monkeypatch):
    calls: list[tuple[int, int]] = []

    def _fake_resolve(session, job_id, candidate_id, entity_id):
        calls.append((candidate_id, entity_id))
        return {"id": candidate_id, "suggested_entity_id": entity_id}

    monkeypatch.setattr(
        "app.services.imports.cst_resolution_plan_apply_sync.resolve_cst_candidate_sync",
        _fake_resolve,
    )
    monkeypatch.setattr(
        "app.services.imports.cst_resolution_plan_apply_sync.build_cst_resolution_plan_sync",
        lambda session, job_id, candidate_ids=None: {
            "rows": [
                {
                    "candidate_id": 10,
                    "ready": True,
                    "suggested_target_id": 101,
                    "plan_class": "ready_to_map",
                },
                {
                    "candidate_id": 11,
                    "ready": True,
                    "suggested_target_id": 202,
                    "plan_class": "ready_to_map",
                },
                {
                    "candidate_id": 12,
                    "ready": False,
                    "suggested_target_id": None,
                    "plan_class": "needs_review",
                },
            ]
        },
    )
    session = MagicMock()
    out = run_cst_resolution_plan_apply_orchestrator(
        session, 1, {"candidate_ids": [10, 11, 12]}
    )
    assert out["applied"] == 2
    assert out["skipped_not_ready"] == 1
    assert calls == [(10, 101), (11, 202)]
    session.commit.assert_called_once()


def test_task_names_and_slot_not_main():
    assert TASK_CST_RESOLUTION_PLAN_COMPUTE == "imports.cst_resolution_plan_compute"
    assert TASK_CST_RESOLUTION_PLAN_APPLY == "imports.cst_resolution_plan_apply"
    assert SLOT_CST_RESOLUTION_PLAN != SLOT_MAIN
    assert "cst_resolution_plan_task" in slot_meta_keys()


def test_set_clear_cst_resolution_plan_slot():
    job = SimpleNamespace(id=9, staged_metadata={})
    set_task_slot_on_job(
        job, SLOT_CST_RESOLUTION_PLAN, task_id="tid-cst", async_poll=True, label="Computing…"
    )
    assert job.staged_metadata["cst_resolution_plan_task"]["task_id"] == "tid-cst"
    clear_task_slot_on_job(job, SLOT_CST_RESOLUTION_PLAN)
    assert "cst_resolution_plan_task" not in (job.staged_metadata or {})
