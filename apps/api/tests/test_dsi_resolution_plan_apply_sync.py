"""Tests for DSI resolution plan apply orchestrator (bulk writers, not per-row replan)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.imports.dsi_resolution_plan import apply_dsi_resolution_plan_rows
from app.services.imports.dsi_resolution_plan_apply_sync import (
    _classify_plan_rows,
    _finalize_apply_result,
    run_dsi_resolution_plan_apply_orchestrator,
    run_dsi_resolution_plan_apply_sync,
)


def _product_cand(cid: int = 9001) -> MagicMock:
    cand = MagicMock()
    cand.id = cid
    cand.import_job_id = 43
    cand.entity_type = "product_identifier"
    cand.context = {
        "product_match_status": "ambiguous_eligible",
        "product_ambiguous_eligible": {"product_ids": [10, 20], "tier": "sales_model_name"},
    }
    return cand


def _effective_resolve_product_row(
    *,
    candidate_id: int,
    target_id: int,
    reason: str,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "entity_type": "product_identifier",
        "ready": True,
        "plan_status": "ready",
        "suggested_action": "resolve_product",
        "suggested_target_id": target_id,
        "baseline_suggested_action": "resolve_product",
        "baseline_ready": False,
        "baseline_target_id": None,
        "hold_for_manual_review": False,
        "resolution_blockers": [],
        "reason": reason,
    }


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


def test_orchestrator_passes_classify_time_rows_to_fallback_apply() -> None:
    session = MagicMock()
    tie_row = _effective_resolve_product_row(
        candidate_id=501,
        target_id=101,
        reason="Shipment evidence tie-break (shipment) — single Product Master match",
    )
    global_row = _effective_resolve_product_row(
        candidate_id=502,
        target_id=202,
        reason="Global shipment identity: sole resolved product across all evidence",
    )
    plan = {"rows": [tie_row, global_row]}
    fallback_out = {
        "import_job_id": 43,
        "applied": 2,
        "failed": 0,
        "skipped_hold": 0,
        "skipped_not_ready": 0,
        "results": [],
    }

    with (
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync.build_dsi_resolution_plan_effective_sync",
            return_value=plan,
        ),
        patch(
            "app.services.imports.dsi_resolution_plan_apply_sync.apply_dsi_resolution_plan_rows",
            new_callable=AsyncMock,
            return_value=fallback_out,
        ) as apply_rows,
        patch("app.services.imports.dsi_resolution_plan_apply_sync._persist_dsi_steward_apply_checkpoint"),
        patch("app.services.imports.dsi_resolution_plan_apply_sync.AsyncSessionLocal") as session_local,
    ):
        mock_db = AsyncMock()
        session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        session_local.return_value.__aexit__ = AsyncMock(return_value=None)
        out = run_dsi_resolution_plan_apply_orchestrator(
            session,
            43,
            {
                "candidate_ids": [501, 502],
                "confirm_for_suspicious_distributor_token": False,
            },
        )

    apply_rows.assert_awaited_once()
    args, kwargs = apply_rows.call_args
    assert args[1] == 43
    assert args[2] == [501, 502]
    assert kwargs["effective_plan_rows_by_cid"] == {501: tie_row, 502: global_row}
    assert out["applied"] == 2


def test_apply_rows_resolve_product_uses_classify_time_target_without_replan() -> None:
    cid = 9001
    target_id = 101
    effective_row = _effective_resolve_product_row(
        candidate_id=cid,
        target_id=target_id,
        reason="Shipment evidence tie-break (shipment) — single Product Master match",
    )
    job = MagicMock()
    cand = _product_cand(cid)

    async def _run() -> None:
        db = AsyncMock()
        db.get = AsyncMock(side_effect=lambda model, pk: job if pk == 43 else cand)
        db.run_sync = AsyncMock()

        with (
            patch(
                "app.services.imports.dsi_resolution_plan.plan_dsi_candidate_sync",
                side_effect=AssertionError("must not replan when classify-time row supplied"),
            ),
            patch(
                "app.services.imports.dsi_resolution_plan.execute_resolve_dsi_product",
                new_callable=AsyncMock,
                return_value={"product_id": target_id},
            ) as exec_resolve,
        ):
            out = await apply_dsi_resolution_plan_rows(
                db,
                43,
                [cid],
                default_region_id=None,
                default_channel_id=None,
                partner_tier=None,
                provisional_notes_summary=None,
                confirm_for_suspicious_distributor_token=False,
                effective_plan_rows_by_cid={cid: effective_row},
            )

        assert out["applied"] == 1
        assert out["skipped_not_ready"] == 0
        db.run_sync.assert_not_awaited()
        exec_resolve.assert_awaited_once()
        assert exec_resolve.await_args.kwargs["product_id"] == target_id
        assert exec_resolve.await_args.kwargs["confirm_ineligible_product"] is False

    asyncio.run(_run())


def test_apply_rows_global_identity_target_preserved_without_replan() -> None:
    cid = 9002
    target_id = 202
    effective_row = _effective_resolve_product_row(
        candidate_id=cid,
        target_id=target_id,
        reason="Global shipment identity: sole resolved product across all evidence",
    )
    job = MagicMock()
    cand = _product_cand(cid)

    async def _run() -> None:
        db = AsyncMock()
        db.get = AsyncMock(side_effect=lambda model, pk: job if pk == 43 else cand)

        with (
            patch(
                "app.services.imports.dsi_resolution_plan.plan_dsi_candidate_sync",
                side_effect=AssertionError("must not replan when classify-time row supplied"),
            ),
            patch(
                "app.services.imports.dsi_resolution_plan.execute_resolve_dsi_product",
                new_callable=AsyncMock,
                return_value={"product_id": target_id},
            ) as exec_resolve,
        ):
            out = await apply_dsi_resolution_plan_rows(
                db,
                43,
                [cid],
                default_region_id=None,
                default_channel_id=None,
                partner_tier=None,
                provisional_notes_summary=None,
                confirm_for_suspicious_distributor_token=False,
                effective_plan_rows_by_cid={cid: effective_row},
            )

        assert out["applied"] == 1
        exec_resolve.assert_awaited_once_with(
            db,
            cand,
            product_id=target_id,
            raw_token=None,
            confirm_ineligible_product=False,
            audit_note=None,
            idempotency_key=None,
        )

    asyncio.run(_run())


def test_apply_rows_inactive_product_still_requires_confirm_at_apply() -> None:
    cid = 9003
    target_id = 303
    effective_row = _effective_resolve_product_row(
        candidate_id=cid,
        target_id=target_id,
        reason="Single Product Master match (item_code) — propose ProductAlias bind",
    )
    job = MagicMock()
    cand = _product_cand(cid)
    cand.context = {"product_match_status": "inactive_only", "product_inactive_matches": [{}]}

    async def _run() -> None:
        db = AsyncMock()
        db.get = AsyncMock(side_effect=lambda model, pk: job if pk == 43 else cand)

        with patch(
            "app.services.imports.dsi_resolution_plan.execute_resolve_dsi_product",
            new_callable=AsyncMock,
        ) as exec_resolve:
            out = await apply_dsi_resolution_plan_rows(
                db,
                43,
                [cid],
                default_region_id=None,
                default_channel_id=None,
                partner_tier=None,
                provisional_notes_summary=None,
                confirm_for_suspicious_distributor_token=False,
                effective_plan_rows_by_cid={cid: effective_row},
            )

        assert out["applied"] == 0
        assert out["skipped_not_ready"] == 1
        assert "inactive_or_ineligible_product_requires_confirm_and_audit_note" in out["results"][0]["detail"]
        exec_resolve.assert_not_awaited()

    asyncio.run(_run())


def test_apply_rows_inactive_product_applies_with_confirm_override() -> None:
    cid = 9004
    target_id = 404
    effective_row = _effective_resolve_product_row(
        candidate_id=cid,
        target_id=target_id,
        reason="Single Product Master match (item_code) — propose ProductAlias bind",
    )
    job = MagicMock()
    cand = _product_cand(cid)
    cand.context = {"product_match_status": "inactive_only", "product_inactive_matches": [{}]}

    async def _run() -> None:
        db = AsyncMock()
        db.get = AsyncMock(side_effect=lambda model, pk: job if pk == 43 else cand)

        with patch(
            "app.services.imports.dsi_resolution_plan.execute_resolve_dsi_product",
            new_callable=AsyncMock,
            return_value={"product_id": target_id},
        ) as exec_resolve:
            out = await apply_dsi_resolution_plan_rows(
                db,
                43,
                [cid],
                default_region_id=None,
                default_channel_id=None,
                partner_tier=None,
                provisional_notes_summary=None,
                confirm_for_suspicious_distributor_token=False,
                overrides=[
                    {
                        "candidate_id": cid,
                        "confirm_ineligible_product": True,
                        "audit_note": "Steward confirmed inactive bind for historical cleanup.",
                    }
                ],
                effective_plan_rows_by_cid={cid: effective_row},
            )

        assert out["applied"] == 1
        exec_resolve.assert_awaited_once()
        assert exec_resolve.await_args.kwargs["confirm_ineligible_product"] is True
        assert exec_resolve.await_args.kwargs["audit_note"] == "Steward confirmed inactive bind for historical cleanup."

    asyncio.run(_run())
