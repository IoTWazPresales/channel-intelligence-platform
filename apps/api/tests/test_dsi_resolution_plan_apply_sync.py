"""Tests for DSI resolution plan apply orchestrator (bulk writers, not per-row replan)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.imports.dsi_resolution_plan_apply_sync import (
    _classify_plan_rows,
    _finalize_apply_result,
    run_dsi_resolution_plan_apply_orchestrator,
    run_dsi_resolution_plan_apply_sync,
)


def test_classify_plan_rows_groups_by_action() -> None:
    combined = {
        "import_job_id": 43,
        "applied": 0,
        "failed": 0,
        "skipped_hold": 0,
        "skipped_not_ready": 0,
        "results": [],
    }
    rows = {
        1: {
            "candidate_id": 1,
            "ready": True,
            "suggested_action": "create_provisional_customer",
            "effective_region_id": 10,
            "effective_channel_id": 20,
        },
        2: {
            "candidate_id": 2,
            "ready": True,
            "suggested_action": "map_customer",
            "suggested_target_id": 328,
        },
        3: {"candidate_id": 3, "ready": False, "resolution_blockers": ["duplicate_review_required"]},
        4: {"candidate_id": 4, "hold_for_manual_review": True, "ready": False},
    }
    prov, geo, mc, md, ign, fb = _classify_plan_rows([1, 2, 3, 4], rows, combined)
    assert prov == [1]
    assert geo == [{"candidate_id": 1, "region_id": 10, "channel_id": 20}]
    assert mc == {328: [2]}
    assert md == {}
    assert ign == []
    assert fb == []
    assert combined["skipped_not_ready"] == 1
    assert combined["skipped_hold"] == 1


def test_orchestrator_routes_provisional_to_bulk_sync() -> None:
    session = MagicMock()
    plan = {
        "rows": [
            {
                "candidate_id": 101,
                "ready": True,
                "suggested_action": "create_provisional_customer",
                "effective_region_id": 5,
            }
        ]
    }
    bulk_out = {
        "results": [{"candidate_id": 101, "ok": True, "result": {"customer_id": 999}}],
        "applied": 1,
        "failed": 0,
    }

    with (
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync.build_dsi_resolution_plan_effective_sync",
            return_value=plan,
        ) as build,
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync.run_dsi_bulk_provisional_customers_sync",
            return_value=bulk_out,
        ) as bulk,
        patch("app.services.imports.dsi_resolution_plan_apply_sync._persist_dsi_steward_apply_checkpoint"),
    ):
        out = run_dsi_resolution_plan_apply_orchestrator(
            session,
            43,
            {
                "candidate_ids": [101],
                "default_region_id": None,
                "default_channel_id": None,
                "confirm_for_suspicious_distributor_token": False,
            },
        )

    build.assert_called_once()
    bulk.assert_called_once()
    payload = bulk.call_args[0][2]
    assert payload["candidate_ids"] == [101]
    assert payload["per_candidate_geo"] == [{"candidate_id": 101, "region_id": 5}]
    assert out["applied"] == 1
    assert out["results"][0]["status"] == "applied"
    assert out["processed"] == 1
    assert out["partial_success"] is False


def test_finalize_apply_result_partial_on_interrupt() -> None:
    combined = {
        "import_job_id": 43,
        "applied": 50,
        "failed": 2,
        "skipped_hold": 0,
        "skipped_not_ready": 0,
        "results": [],
    }
    out = _finalize_apply_result(combined, processed=52, total=100, interrupted=True, error="ssl closed")
    assert out["partial_success"] is True
    assert out["interrupted"] is True
    assert out["processed"] == 52
    assert out["error"] == "ssl closed"


def test_apply_sync_returns_partial_when_checkpoint_shows_progress() -> None:
    with (
        patch("app.services.imports.dsi_resolution_plan_apply_sync.SessionLocal") as mock_local,
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync.run_dsi_resolution_plan_apply_orchestrator",
            side_effect=RuntimeError("connection reset"),
        ),
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync._read_dsi_steward_apply_checkpoint",
            return_value={
                "processed": 40,
                "total": 100,
                "applied": 38,
                "failed": 2,
            },
        ),
        patch("app.services.imports.dsi_resolution_plan_apply_sync._persist_dsi_steward_apply_checkpoint"),
    ):
        mock_local.return_value.__enter__.return_value = MagicMock()
        out = run_dsi_resolution_plan_apply_sync(
            43,
            {"candidate_ids": list(range(100)), "confirm_for_suspicious_distributor_token": False},
        )

    assert out["partial_success"] is True
    assert out["applied"] == 38
    assert out["processed"] == 40


def test_apply_sync_uses_single_session_orchestrator() -> None:
    with (
        patch("app.services.imports.dsi_resolution_plan_apply_sync.SessionLocal") as mock_local,
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync.run_dsi_resolution_plan_apply_orchestrator",
            return_value={"import_job_id": 43, "applied": 2, "failed": 0, "skipped_hold": 0, "skipped_not_ready": 0, "results": []},
        ) as orch,
    ):
        mock_local.return_value.__enter__.return_value = MagicMock()
        out = run_dsi_resolution_plan_apply_sync(
            43,
            {"candidate_ids": [1, 2], "confirm_for_suspicious_distributor_token": False},
            on_progress=lambda *_a: None,
        )

    orch.assert_called_once()
    assert out["applied"] == 2
    assert out["processed"] == 2
    assert out["partial_success"] is False
