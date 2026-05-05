"""DSI resolution plan classification (no database)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.services.imports.dsi_resolution_plan import (
    merge_resolution_plan_row_for_apply,
    plan_dsi_candidate_sync,
    snapshot_product_plan_from_context,
)


def _cand(**kwargs: object) -> MagicMock:
    c = MagicMock()
    c.id = kwargs.get("id", 1)
    c.entity_type = kwargs.get("entity_type", "distributor_token")
    c.status = kwargs.get("status", "open")
    c.normalized_key = kwargs.get("normalized_key", "tok")
    c.context = kwargs.get("context", {})
    c.row_count = kwargs.get("row_count", 1)
    c.total_units = kwargs.get("total_units")
    c.total_reported_value = kwargs.get("total_reported_value")
    c.dealer_group_token = kwargs.get("dealer_group_token")
    return c


def test_snapshot_product_ambiguous_is_manual_review() -> None:
    out = snapshot_product_plan_from_context({"product_match_status": "ambiguous_eligible"})
    assert out["ready"] is False
    assert out.get("reason") == "ambiguous"


def test_snapshot_product_inactive_only_is_manual_review() -> None:
    out = snapshot_product_plan_from_context({"product_match_status": "inactive_only", "product_inactive_matches": [{}]})
    assert out["ready"] is False
    assert out.get("reason") == "inactive_only"


def test_snapshot_product_empty_context() -> None:
    out = snapshot_product_plan_from_context(None)
    assert out["ready"] is False


def test_plan_distributor_maps_existing() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(entity_type="distributor_token")
    with patch(
        "app.services.imports.dsi_resolution_plan.dsi_first_sample", return_value="ACME DIST"
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_distributor",
        return_value=(401, None),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["suggested_action"] == "map_distributor"
    assert out["ready"] is True
    assert out["suggested_target_id"] == 401


def test_plan_distributor_placeholder_ignore() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(entity_type="distributor_token")
    with patch("app.services.imports.dsi_resolution_plan.dsi_first_sample", return_value="unknown"), patch(
        "app.services.imports.dsi_resolution_plan._resolve_distributor",
        return_value=(None, "no match"),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["suggested_action"] == "ignore"
    assert out["ready"] is True


def test_plan_distributor_provisional_when_no_match() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(entity_type="distributor_token")
    with patch("app.services.imports.dsi_resolution_plan.dsi_first_sample", return_value="New Dist LLC"), patch(
        "app.services.imports.dsi_resolution_plan._resolve_distributor",
        return_value=(None, "no match"),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["suggested_action"] == "create_provisional_distributor"
    assert out["ready"] is True


def test_plan_product_single_match_ready() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="product_identifier",
        context={"product_match_status": "single_eligible"},
    )
    with patch("app.services.imports.dsi_resolution_plan.dsi_first_sample", return_value="SKU-1"), patch(
        "app.services.imports.dsi_resolution_plan._resolve_product",
        return_value=(9001, None, "alias", {}),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["suggested_action"] == "resolve_product"
    assert out["ready"] is True
    assert out["suggested_target_id"] == 9001


def test_plan_product_ambiguous_not_ready() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="product_identifier",
        context={"product_match_status": "ambiguous_eligible"},
    )
    with patch("app.services.imports.dsi_resolution_plan.dsi_first_sample", return_value="SKU-X"):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["ready"] is False
    assert out["plan_status"] == "needs_review"


def test_plan_customer_maps_existing() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["Alias Name"],
            "dealer_group_account_raw": "DG1",
        },
    )
    with patch(
        "app.services.imports.dsi_resolution_plan.effective_dsi_customer_primary_for_resolution",
        return_value=("Alias Name", []),
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_customer",
        return_value=(55, ["exact_name"]),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["suggested_action"] == "map_customer"
    assert out["ready"] is True
    assert out["suggested_target_id"] == 55


def test_plan_customer_provisional_needs_defaults_without_region_channel() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
        },
    )
    with patch(
        "app.services.imports.dsi_resolution_plan.effective_dsi_customer_primary_for_resolution",
        return_value=("New Customer", []),
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_customer",
        return_value=(None, ["nomatch"]),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=None, default_channel_id=None)
    assert out["suggested_action"] == "create_provisional_customer"
    assert out["ready"] is False
    assert out["needs_defaults"] is True


def test_plan_customer_provisional_ready_with_defaults() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
        },
    )
    with patch(
        "app.services.imports.dsi_resolution_plan.effective_dsi_customer_primary_for_resolution",
        return_value=("New Customer", []),
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_customer",
        return_value=(None, ["nomatch"]),
    ):
        out = plan_dsi_candidate_sync(
            sess, cand, job, prod_idx, default_region_id=10, default_channel_id=20
        )
    assert out["suggested_action"] == "create_provisional_customer"
    assert out["ready"] is True
    assert out["needs_defaults"] is False


def test_plan_customer_ambiguous_name_manual() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={"source_customer_name_raw_samples": ["X"], "dealer_group_account_raw": "DG"},
    )
    with patch(
        "app.services.imports.dsi_resolution_plan.effective_dsi_customer_primary_for_resolution",
        return_value=("X", []),
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_customer",
        return_value=(None, ["ambiguous_customer_name"]),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=10, default_channel_id=20)
    assert out["ready"] is False
    assert "Ambiguous" in str(out.get("reason", ""))


def test_dsi_resolution_plan_generate_body_defaults() -> None:
    from app.api.v1.endpoints.mappings import DsiResolutionPlanGenerateBody

    b = DsiResolutionPlanGenerateBody()
    assert b.candidate_ids is None
    assert b.default_region_id is None


def test_dsi_resolution_plan_apply_body_requires_candidate_ids() -> None:
    from app.api.v1.endpoints.mappings import DsiResolutionPlanApplyBody

    with pytest.raises(ValidationError):
        DsiResolutionPlanApplyBody(candidate_ids=[])

    b = DsiResolutionPlanApplyBody(candidate_ids=[1, 2], default_region_id=3, default_channel_id=4)
    assert b.candidate_ids == [1, 2]


def test_dsi_resolution_plan_apply_body_accepts_overrides() -> None:
    from app.api.v1.endpoints.mappings import DsiResolutionPlanApplyBody

    b = DsiResolutionPlanApplyBody(
        candidate_ids=[1],
        overrides=[{"candidate_id": 1, "action": "ignore", "hold_for_manual_review": False}],
    )
    assert b.overrides is not None
    assert b.overrides[0].candidate_id == 1


def test_dsi_resolution_plan_effective_body_default_overrides() -> None:
    from app.api.v1.endpoints.mappings import DsiResolutionPlanEffectiveBody

    b = DsiResolutionPlanEffectiveBody()
    assert b.overrides == []


def test_merge_hold_for_manual_review() -> None:
    cand = _cand(entity_type="distributor_token")
    base = {"suggested_action": "map_distributor", "suggested_target_id": 1, "ready": True}
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={"hold_for_manual_review": True},
        default_region_id=None,
        default_channel_id=None,
        global_confirm_suspicious_distributor=False,
    )
    assert m["hold_for_manual_review"] is True
    assert m["effective_ready"] is False


def test_merge_placeholder_distributor_override_create_requires_confirm() -> None:
    cand = _cand(entity_type="distributor_token")
    base = {"suggested_action": "ignore", "suggested_target_id": None, "ready": True}
    with patch(
        "app.services.imports.dsi_resolution_plan.distributor_token_is_placeholder_like", return_value=True
    ):
        m = merge_resolution_plan_row_for_apply(
            cand=cand,
            base=base,
            ov={"action": "create_provisional_distributor"},
            default_region_id=None,
            default_channel_id=None,
            global_confirm_suspicious_distributor=False,
        )
    assert m["effective_ready"] is False
    assert "placeholder_like_distributor_requires_confirm" in m["blockers"]


def test_merge_placeholder_distributor_override_create_ok_with_row_confirm() -> None:
    cand = _cand(entity_type="distributor_token")
    base = {"suggested_action": "ignore", "suggested_target_id": None, "ready": True}
    with patch(
        "app.services.imports.dsi_resolution_plan.distributor_token_is_placeholder_like", return_value=True
    ):
        m = merge_resolution_plan_row_for_apply(
            cand=cand,
            base=base,
            ov={"action": "create_provisional_distributor", "confirm_for_suspicious_distributor_token": True},
            default_region_id=None,
            default_channel_id=None,
            global_confirm_suspicious_distributor=False,
        )
    assert m["effective_ready"] is True


def test_merge_placeholder_distributor_override_create_ok_with_global_confirm() -> None:
    cand = _cand(entity_type="distributor_token")
    base = {"suggested_action": "ignore", "suggested_target_id": None, "ready": True}
    with patch(
        "app.services.imports.dsi_resolution_plan.distributor_token_is_placeholder_like", return_value=True
    ):
        m = merge_resolution_plan_row_for_apply(
            cand=cand,
            base=base,
            ov={"action": "create_provisional_distributor"},
            default_region_id=None,
            default_channel_id=None,
            global_confirm_suspicious_distributor=True,
        )
    assert m["effective_ready"] is True


def test_merge_product_inactive_requires_audit_note() -> None:
    cand = _cand(entity_type="product_identifier", context={"product_match_status": "inactive_only"})
    base = {"suggested_action": "resolve_product", "suggested_target_id": None, "ready": False}
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={"action": "resolve_product", "target_id": 99},
        default_region_id=None,
        default_channel_id=None,
        global_confirm_suspicious_distributor=False,
    )
    assert m["effective_ready"] is False
    assert "inactive_or_ineligible_product_requires_confirm_and_audit_note" in m["blockers"]


def test_merge_product_inactive_ok_with_confirm_and_audit() -> None:
    cand = _cand(entity_type="product_identifier", context={"product_match_status": "inactive_only"})
    base = {"suggested_action": "resolve_product", "suggested_target_id": None, "ready": False}
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={
            "action": "resolve_product",
            "target_id": 99,
            "confirm_ineligible_product": True,
            "audit_note": "12345678",
        },
        default_region_id=None,
        default_channel_id=None,
        global_confirm_suspicious_distributor=False,
    )
    assert m["effective_ready"] is True


def test_merge_strategic_customer_provisional_requires_ack() -> None:
    cand = _cand(entity_type="customer_dealer_token", context={"strategic_channel_hint": True})
    base = {"suggested_action": "create_provisional_customer", "suggested_target_id": None, "ready": False}
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={"action": "create_provisional_customer"},
        default_region_id=10,
        default_channel_id=20,
        global_confirm_suspicious_distributor=False,
    )
    assert "strategic_channel_hint_ack_required" in m["blockers"]


def test_merge_strategic_customer_provisional_ok_with_ack() -> None:
    cand = _cand(entity_type="customer_dealer_token", context={"strategic_channel_hint": True})
    base = {"suggested_action": "create_provisional_customer", "suggested_target_id": None, "ready": False}
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={"action": "create_provisional_customer", "ack_strategic_channel_hint": True},
        default_region_id=10,
        default_channel_id=20,
        global_confirm_suspicious_distributor=False,
    )
    assert m["effective_ready"] is True
