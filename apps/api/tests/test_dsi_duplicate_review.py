"""DSI duplicate review steward decisions and resolution plan gating."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.imports.dsi_customer_intelligence import (
    build_duplicate_review_record,
    dsi_candidate_duplicate_review_unresolved,
    duplicate_review_decision,
    gate_dsi_plan_row_duplicate_review,
)
from app.services.imports.dsi_resolution_plan import merge_resolution_plan_row_for_apply
from app.services.imports.dsi_steward_candidate_ops import (
    StewardOpError,
    execute_dsi_duplicate_same_entity,
    resolve_duplicate_same_entity_customer_id,
)


def _customer_cand(
    *,
    ctx: dict,
    status: str = "needs_review",
    cand_id: int = 1,
    normalized_key: str = "acme",
    suggested_entity_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=cand_id,
        import_job_id=10,
        entity_type="customer_dealer_token",
        normalized_key=normalized_key,
        dealer_group_token=None,
        row_count=5,
        total_units=1.0,
        total_reported_value=None,
        sample_raw_values=["Acme Retail"],
        status=status,
        context=ctx,
        suggested_entity_id=suggested_entity_id,
        match_reason=None,
        confidence_score=None,
        source_definition_id=1,
    )


def test_duplicate_review_unresolved_when_hints_without_decision() -> None:
    cand = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    )
    assert dsi_candidate_duplicate_review_unresolved(cand) is True


def test_duplicate_review_resolved_when_decision_present() -> None:
    cand = _customer_cand(
        ctx={
            "possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}],
            "duplicate_review": build_duplicate_review_record(
                decision="different_entity",
                paired_normalized_key="acme2",
                similarity_score=0.91,
            ),
        },
        status="acknowledged_unique",
    )
    assert dsi_candidate_duplicate_review_unresolved(cand) is False


def test_gate_plan_row_blocks_ready() -> None:
    cand = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.9}]}
    )
    row = {
        "ready": True,
        "plan_status": "ready",
        "suggested_action": "map_customer",
        "reason": "Matched",
        "resolution_blockers": [],
    }
    gated = gate_dsi_plan_row_duplicate_review(cand, row)
    assert gated["ready"] is False
    assert gated["duplicate_review_required"] is True
    assert "duplicate_review_required" in gated["resolution_blockers"]


def test_merge_apply_blocks_when_duplicate_unresolved() -> None:
    cand = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.9}]}
    )
    base = {
        "suggested_action": "map_customer",
        "suggested_target_id": 42,
        "ready": True,
        "effective_region_id": None,
        "effective_channel_id": None,
    }
    merged = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov=None,
        default_region_id=None,
        default_channel_id=None,
        global_confirm_suspicious_distributor=False,
    )
    assert merged["effective_ready"] is False
    assert "duplicate_review_required" in merged["blockers"]


def test_acknowledged_unique_not_terminal_for_steward() -> None:
    from app.services.imports.dsi_resolution_plan import _terminal_candidate

    cand = _customer_cand(ctx={}, status="acknowledged_unique")
    assert _terminal_candidate(cand) is False


def test_resolve_same_entity_customer_id_explicit_wins() -> None:
    cid, prov = resolve_duplicate_same_entity_customer_id(
        customer_id=99,
        primary_suggested_entity_id=1,
        peer_suggested_entity_id=2,
    )
    assert cid == 99
    assert prov is False


def test_resolve_same_entity_customer_id_conflict() -> None:
    with pytest.raises(StewardOpError) as exc:
        resolve_duplicate_same_entity_customer_id(
            customer_id=None,
            primary_suggested_entity_id=10,
            peer_suggested_entity_id=20,
        )
    assert exc.value.status_code == 409


def test_resolve_same_entity_customer_id_greenfield() -> None:
    cid, prov = resolve_duplicate_same_entity_customer_id(
        customer_id=None,
        primary_suggested_entity_id=None,
        peer_suggested_entity_id=None,
    )
    assert cid == 0
    assert prov is True


def test_resolve_same_entity_customer_id_single_suggestion() -> None:
    cid, prov = resolve_duplicate_same_entity_customer_id(
        customer_id=None,
        primary_suggested_entity_id=None,
        peer_suggested_entity_id=55,
    )
    assert cid == 55
    assert prov is False


def test_resolve_same_entity_customer_id_plan_suggestion() -> None:
    cid, prov = resolve_duplicate_same_entity_customer_id(
        customer_id=None,
        primary_suggested_entity_id=None,
        peer_suggested_entity_id=None,
        plan_suggested_target_id=88,
    )
    assert cid == 88
    assert prov is False


def test_same_entity_display_name_forces_provisional_create() -> None:
    asyncio.run(_run_same_entity_display_name_forces_provisional_create())


async def _run_same_entity_display_name_forces_provisional_create() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1, normalized_key="acme")
    peer = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme", "similarity_score": 0.91}]},
        cand_id=2,
        normalized_key="acme2",
        suggested_entity_id=55,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
            return_value=601,
        ) as create_prov,
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
            side_effect=[
                {"ok": True, "alias_id": 1, "customer_id": 601, "candidate_id": 1},
                {"ok": True, "alias_id": 2, "customer_id": 601, "candidate_id": 2},
            ],
        ) as map_apply,
    ):
        out = await execute_dsi_duplicate_same_entity(
            db,
            primary,
            peer_normalized_key="acme2",
            customer_id=None,
            display_name="Rectron Cape Town",
            plan_suggested_target_id=55,
            raw_token=None,
            audit_note="grouped",
        )

    create_prov.assert_awaited_once()
    assert create_prov.await_args.kwargs["display_name_override"] == "Rectron Cape Town"
    map_apply.assert_awaited()
    assert out["customer_id"] == 601
    assert out["created_provisional"]["display_name"] == "Rectron Cape Town"


def test_same_entity_display_name_null_uses_default_resolution() -> None:
    asyncio.run(_run_same_entity_display_name_null_uses_default_resolution())


async def _run_same_entity_display_name_null_uses_default_resolution() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1)
    peer = _customer_cand(ctx={}, cand_id=2, normalized_key="acme2")
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
            return_value=501,
        ) as create_prov,
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
            side_effect=[
                {"ok": True, "alias_id": 1, "customer_id": 501, "candidate_id": 1},
                {"ok": True, "alias_id": 2, "customer_id": 501, "candidate_id": 2},
            ],
        ),
    ):
        await execute_dsi_duplicate_same_entity(
            db,
            primary,
            peer_normalized_key="acme2",
            customer_id=None,
            display_name=None,
            plan_suggested_target_id=None,
            raw_token=None,
            audit_note=None,
        )

    create_prov.assert_awaited_once()
    assert create_prov.await_args.kwargs["display_name_override"] is None


def test_same_entity_plan_target_without_explicit_customer_id() -> None:
    asyncio.run(_run_same_entity_plan_target_without_explicit_customer_id())


async def _run_same_entity_plan_target_without_explicit_customer_id() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1)
    peer = _customer_cand(ctx={}, cand_id=2, normalized_key="acme2")
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
        ) as create_prov,
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
            side_effect=[
                {"ok": True, "alias_id": 1, "customer_id": 88, "candidate_id": 1},
                {"ok": True, "alias_id": 2, "customer_id": 88, "candidate_id": 2},
            ],
        ),
    ):
        out = await execute_dsi_duplicate_same_entity(
            db,
            primary,
            peer_normalized_key="acme2",
            customer_id=None,
            display_name=None,
            plan_suggested_target_id=88,
            raw_token=None,
            audit_note=None,
        )

    create_prov.assert_not_awaited()
    assert out["customer_id"] == 88
    assert duplicate_review_decision(primary.context) == "same_entity"


def test_same_entity_greenfield_creates_provisional_and_maps_both() -> None:
    asyncio.run(_run_same_entity_greenfield_creates_provisional_and_maps_both())


async def _run_same_entity_greenfield_creates_provisional_and_maps_both() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1, normalized_key="acme")
    peer = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme", "similarity_score": 0.91}]},
        cand_id=2,
        normalized_key="acme2",
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
            return_value=501,
        ) as create_prov,
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
            side_effect=[
                {"ok": True, "alias_id": 1, "customer_id": 501, "candidate_id": 1},
                {"ok": True, "alias_id": 2, "customer_id": 501, "candidate_id": 2},
            ],
        ) as map_apply,
    ):
        out = await execute_dsi_duplicate_same_entity(
            db,
            primary,
            peer_normalized_key="acme2",
            customer_id=None,
            raw_token=None,
            audit_note="note",
        )

    create_prov.assert_awaited_once()
    assert map_apply.await_count == 2
    db.commit.assert_awaited_once()
    assert out["customer_id"] == 501
    assert out["created_provisional"] == {"customer_id": 501}
    assert duplicate_review_decision(primary.context) == "same_entity"
    assert duplicate_review_decision(peer.context) == "same_entity"
    assert primary.context["duplicate_review"]["customer_id"] == 501


def test_same_entity_explicit_customer_id_maps_both() -> None:
    asyncio.run(_run_same_entity_explicit_customer_id_maps_both())


async def _run_same_entity_explicit_customer_id_maps_both() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1)
    peer = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme", "similarity_score": 0.91}]},
        cand_id=2,
        normalized_key="acme2",
        suggested_entity_id=42,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
        ) as create_prov,
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
            side_effect=[
                {"ok": True, "alias_id": 1, "customer_id": 77, "candidate_id": 1},
                {"ok": True, "alias_id": 2, "customer_id": 77, "candidate_id": 2},
            ],
        ) as map_apply,
    ):
        out = await execute_dsi_duplicate_same_entity(
            db,
            primary,
            peer_normalized_key="acme2",
            customer_id=77,
            raw_token=None,
            audit_note=None,
        )

    create_prov.assert_not_awaited()
    assert map_apply.await_count == 2
    assert out["customer_id"] == 77
    assert out["created_provisional"] is None


def test_same_entity_conflicting_suggestions_409() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, suggested_entity_id=10)
    peer = _customer_cand(
        ctx={},
        cand_id=2,
        normalized_key="acme2",
        suggested_entity_id=20,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    with pytest.raises(StewardOpError) as exc:
        asyncio.run(
            execute_dsi_duplicate_same_entity(
                db,
                primary,
                peer_normalized_key="acme2",
                customer_id=None,
                raw_token=None,
                audit_note=None,
            )
        )
    assert exc.value.status_code == 409
    db.commit.assert_not_awaited()


def test_same_entity_peer_map_failure_rolls_back() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1)
    peer = _customer_cand(ctx={}, cand_id=2, normalized_key="acme2")
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with patch(
        "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
        new_callable=AsyncMock,
        side_effect=[
            {"ok": True, "alias_id": 1, "customer_id": 88, "candidate_id": 1},
            StewardOpError("peer map failed", status_code=400),
        ],
    ):
        with pytest.raises(StewardOpError):
            asyncio.run(
                execute_dsi_duplicate_same_entity(
                    db,
                    primary,
                    peer_normalized_key="acme2",
                    customer_id=88,
                    raw_token=None,
                    audit_note=None,
                )
            )

    db.rollback.assert_awaited()
    db.commit.assert_not_awaited()
    assert duplicate_review_decision(primary.context) is None


def test_same_entity_self_referential_peer_key_400() -> None:
    asyncio.run(_run_same_entity_self_referential_peer_key_400())


async def _run_same_entity_self_referential_peer_key_400() -> None:
    ctx = {
        "possible_duplicate_of": [
            {"normalized_key": "acme", "similarity_score": 1.0},
            {"normalized_key": "acme2", "similarity_score": 0.91},
        ]
    }
    primary = _customer_cand(ctx=ctx, cand_id=1, normalized_key="acme", status="needs_review")
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=primary)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
        ) as create_prov,
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
        ) as map_apply,
    ):
        with pytest.raises(StewardOpError) as exc:
            await execute_dsi_duplicate_same_entity(
                db,
                primary,
                peer_normalized_key="acme",
                customer_id=None,
                raw_token=None,
                audit_note=None,
            )

    assert exc.value.status_code == 400
    assert "must differ" in exc.value.detail.lower()
    create_prov.assert_not_awaited()
    map_apply.assert_not_awaited()
    db.commit.assert_not_awaited()
    assert primary.status == "needs_review"
    assert duplicate_review_decision(primary.context) is None


def test_same_entity_paired_normalized_key_uses_db_canonical() -> None:
    asyncio.run(_run_same_entity_paired_normalized_key_uses_db_canonical())


async def _run_same_entity_paired_normalized_key_uses_db_canonical() -> None:
    ctx = {"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.91}]}
    primary = _customer_cand(ctx=ctx, cand_id=1, normalized_key="acme")
    peer = _customer_cand(
        ctx={"possible_duplicate_of": [{"normalized_key": "acme", "similarity_score": 0.91}]},
        cand_id=2,
        normalized_key="acme2",
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=peer)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

    with (
        patch(
            "app.services.imports.dsi_steward_candidate_ops._create_provisional_dim_customer_for_same_entity",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.imports.dsi_steward_candidate_ops._apply_map_dsi_customer_without_commit",
            new_callable=AsyncMock,
            side_effect=[
                {"ok": True, "alias_id": 1, "customer_id": 77, "candidate_id": 1},
                {"ok": True, "alias_id": 2, "customer_id": 77, "candidate_id": 2},
            ],
        ),
    ):
        await execute_dsi_duplicate_same_entity(
            db,
            primary,
            peer_normalized_key="  acme2  ",
            customer_id=77,
            raw_token=None,
            audit_note=None,
        )

    assert primary.context["duplicate_review"]["paired_normalized_key"] == "acme2"
    assert peer.context["duplicate_review"]["paired_normalized_key"] == "acme"
