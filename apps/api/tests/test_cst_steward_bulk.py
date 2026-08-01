"""CST steward bulk preview → apply (Unit E S8)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.imports.cst_mapping_candidates import CST_PRODUCT_ENTITY
from app.services.imports.cst_steward_bulk import apply_cst_steward_bulk, preview_cst_steward_bulk


def test_preview_resolve_product_ok_and_terminal_skip():
    open_cand = SimpleNamespace(
        id=1,
        entity_type=CST_PRODUCT_ENTITY,
        normalized_key="sku-a",
        row_count=2,
        status="needs_review",
    )
    ignored = SimpleNamespace(
        id=2,
        entity_type=CST_PRODUCT_ENTITY,
        normalized_key="sku-b",
        row_count=1,
        status="ignored",
    )
    session = MagicMock()
    session.scalars.return_value.all.return_value = [open_cand, ignored]

    out = preview_cst_steward_bulk(
        session, 10, action="resolve_product", candidate_ids=[1, 2, 99], product_id=5
    )
    assert out["totals"]["ok_count"] == 1
    assert out["totals"]["not_ok_count"] == 2
    by_id = {r["candidate_id"]: r for r in out["results"]}
    assert by_id[1]["ok"] is True
    assert by_id[2]["skip_reason"] == "already_terminal"
    assert by_id[99]["skip_reason"] == "not_found_or_wrong_job"


def test_apply_resolve_calls_resolve_sync(monkeypatch):
    calls: list[tuple[int, int]] = []

    def _resolve(_session, job_id, candidate_id, entity_id):
        calls.append((candidate_id, entity_id))
        return {"id": candidate_id}

    monkeypatch.setattr(
        "app.services.imports.cst_steward_bulk.resolve_cst_candidate_sync",
        _resolve,
    )
    open_cand = SimpleNamespace(
        id=7,
        entity_type=CST_PRODUCT_ENTITY,
        normalized_key="sku-a",
        row_count=1,
        status="needs_review",
    )
    session = MagicMock()
    session.scalars.return_value.all.return_value = [open_cand]

    out = apply_cst_steward_bulk(
        session, 3, action="resolve_product", candidate_ids=[7], product_id=42
    )
    assert out["applied"] == 1
    assert out["failed"] == 0
    assert calls == [(7, 42)]
