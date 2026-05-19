"""DSI resolution plan classification (no database)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.services.imports.dsi_resolution_plan import (
    _resolve_dim_channel_from_source,
    build_plan_why_from_candidate,
    derive_effective_provisional_customer_geo_sync,
    dsi_geo_channel_alias_source_id,
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
    c.source_definition_id = kwargs.get("source_definition_id")
    c.import_job_id = kwargs.get("import_job_id")
    return c


def test_build_plan_why_includes_corroboration_and_blockers() -> None:
    cand = _cand(
        entity_type="product_identifier",
        context={
            "product_match_status": "ambiguous_eligible",
            "corroboration_markers": ["shipment_evidence_product"],
            "shipment_evidence_corroboration": {
                "best_match_count": 3,
                "summary": "Shipment lines in month",
            },
        },
    )
    row = {
        "suggested_action": "resolve_product",
        "ready": False,
        "reason": "Multiple eligible Product Master matches",
        "resolution_blockers": ["ambiguous_product"],
    }
    why = build_plan_why_from_candidate(cand, row)
    assert why["rule_path"] == "product.ambiguous_eligible_manual"
    assert "ambiguous_product" in why["blockers"]
    assert len(why["corroboration_hits"]) >= 2


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


def test_plan_customer_provisional_ready_without_defaults_when_no_source_geo() -> None:
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
    assert out["ready"] is True
    assert out["needs_defaults"] is False
    assert out.get("effective_region_id") is None
    assert out.get("effective_channel_id") is None


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
    from app.schemas.dsi_resolution_plan_requests import DsiResolutionPlanGenerateBody

    b = DsiResolutionPlanGenerateBody()
    assert b.candidate_ids is None
    assert b.default_region_id is None


def test_dsi_resolution_plan_apply_body_requires_candidate_ids() -> None:
    from app.schemas.dsi_resolution_plan_requests import DsiResolutionPlanApplyBody

    with pytest.raises(ValidationError):
        DsiResolutionPlanApplyBody(candidate_ids=[])

    b = DsiResolutionPlanApplyBody(candidate_ids=[1, 2], default_region_id=3, default_channel_id=4)
    assert b.candidate_ids == [1, 2]


def test_dsi_resolution_plan_apply_body_accepts_overrides() -> None:
    from app.schemas.dsi_resolution_plan_requests import DsiResolutionPlanApplyBody

    b = DsiResolutionPlanApplyBody(
        candidate_ids=[1],
        overrides=[{"candidate_id": 1, "action": "ignore", "hold_for_manual_review": False}],
    )
    assert b.overrides is not None
    assert b.overrides[0].candidate_id == 1


def test_dsi_resolution_plan_effective_body_default_overrides() -> None:
    from app.schemas.dsi_resolution_plan_requests import DsiResolutionPlanEffectiveBody

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


def test_plan_customer_provisional_resolves_geo_from_source_single_value() -> None:
    sess = MagicMock()
    mr = MagicMock()
    mr.id = 101
    mr.code = "NA-E"
    mr.name = "North America East"
    mc = MagicMock()
    mc.id = 202
    mc.code = "RET"
    mc.name = "Retail"
    sess.scalar = MagicMock(side_effect=[mr, mc])

    def fake_get(_m: object, pk: object) -> MagicMock | None:
        if int(pk) == 101:
            return mr
        if int(pk) == 202:
            return mc
        return None

    sess.get = MagicMock(side_effect=fake_get)

    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
            "source_region_evidence_norms": ["na-e"],
            "source_region_raw_samples": ["NA-E"],
            "source_channel_evidence_norms": ["ret"],
            "source_channel_raw_samples": ["RET"],
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
    assert out["ready"] is True
    assert out.get("suggested_region_id") == 101
    assert out.get("suggested_channel_id") == 202
    assert out.get("effective_region_id") == 101
    assert out.get("effective_channel_id") == 202
    assert out.get("used_global_fallback_region") is False
    assert out.get("used_global_fallback_channel") is False
    assert "File → catalog region" in (out.get("source_region_resolution_message") or "")


def test_plan_customer_provisional_marks_global_fallback_when_source_missing() -> None:
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
            sess, cand, job, prod_idx, default_region_id=99, default_channel_id=88
        )
    assert out["suggested_action"] == "create_provisional_customer"
    assert out["ready"] is True
    assert out.get("used_global_fallback_region") is True
    assert out.get("used_global_fallback_channel") is True
    assert int(out.get("effective_region_id") or 0) == 99
    assert int(out.get("effective_channel_id") or 0) == 88


def test_derive_geo_global_fallback_does_not_trigger_when_source_resolves() -> None:
    """Effective ids prefer source; selecting global defaults must not mark fallback-used for resolved dims."""
    sess = MagicMock()
    mr = MagicMock()
    mr.id = 101
    mr.code = "WC"
    mr.name = "Western Cape"
    mc = MagicMock()
    mc.id = 202
    mc.code = "WHO"
    mc.name = "Wholesale"
    sess.scalar = MagicMock(side_effect=[mr, mc])

    def fake_get(_m: object, pk: object) -> MagicMock | None:
        if int(pk) == 101:
            return mr
        if int(pk) == 202:
            return mc
        return None

    sess.get = MagicMock(side_effect=fake_get)
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_region_evidence_norms": ["western cape"],
            "source_region_raw_samples": ["Western Cape"],
            "source_channel_evidence_norms": ["wholesale"],
            "source_channel_raw_samples": ["Wholesale"],
        },
    )
    g = derive_effective_provisional_customer_geo_sync(
        sess, cand, default_region_id=999, default_channel_id=888, import_job=None
    )
    assert g["effective_region_id"] == 101
    assert g["effective_channel_id"] == 202
    assert g["used_global_fallback_region"] is False
    assert g["used_global_fallback_channel"] is False


def test_plan_customer_provisional_unresolved_source_includes_raw_in_message() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=None)
    sess.get = MagicMock(return_value=None)
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
            "source_region_evidence_norms": ["eastern cape"],
            "source_region_raw_samples": ["Eastern Cape"],
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
    msg = str(out.get("source_region_resolution_message") or "")
    assert "Eastern Cape" in msg
    assert "no_catalog_match" in msg or "no approved source-token mapping" in msg or "has no matching catalog" in msg


def test_plan_customer_provisional_geo_conflict_not_ready() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
            "provisional_region_conflict": True,
            "source_region_evidence_norms": ["a", "b"],
        },
    )
    with patch(
        "app.services.imports.dsi_resolution_plan.effective_dsi_customer_primary_for_resolution",
        return_value=("New Customer", []),
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_customer",
        return_value=(None, ["nomatch"]),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=10, default_channel_id=20)
    assert out["suggested_action"] == "create_provisional_customer"
    assert out["ready"] is False
    assert "Conflicting source evidence" in str(out.get("reason", ""))


def test_merge_provisional_geo_conflict_requires_row_overrides() -> None:
    cand = _cand(
        entity_type="customer_dealer_token",
        context={"provisional_region_conflict": True},
    )
    base = {
        "suggested_action": "create_provisional_customer",
        "suggested_target_id": None,
        "ready": False,
        "effective_region_id": 1,
        "effective_channel_id": 2,
    }
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={"action": "create_provisional_customer"},
        default_region_id=10,
        default_channel_id=20,
        global_confirm_suspicious_distributor=False,
    )
    assert m["effective_ready"] is False
    assert "provisional_geo_conflict_requires_row_region_channel_override" in m["blockers"]


def test_resolve_dim_channel_prefers_catalog_before_alias() -> None:
    ch = MagicMock()
    ch.id = 404
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=ch)
    cid, reason = _resolve_dim_channel_from_source(sess, "RET", source_definition_id=1)
    assert cid == 404
    assert reason == "catalog_match"
    sess.scalars.assert_not_called()


def test_resolve_dim_channel_uses_approved_alias_when_catalog_misses() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=None)
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[303])))
    cid, reason = _resolve_dim_channel_from_source(sess, "Con_Open Channel", source_definition_id=9)
    assert cid == 303
    assert reason == "source_channel_token_alias"


def test_resolve_dim_channel_conflict_when_multiple_alias_targets() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=None)
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[303, 404])))
    cid, reason = _resolve_dim_channel_from_source(sess, "Con_Open Channel", source_definition_id=9)
    assert cid is None
    assert reason == "conflicting_channel_token_aliases"


def test_plan_customer_provisional_resolves_channel_via_token_alias() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=None)
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[202])))
    mc = MagicMock()
    mc.id = 202
    mc.code = "OPEN_CH"
    mc.name = "Open Channel"

    def fake_get(_m: object, pk: object) -> MagicMock | None:
        if int(pk) == 202:
            return mc
        return None

    sess.get = MagicMock(side_effect=fake_get)
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
            "source_channel_evidence_norms": ["con_open channel"],
            "source_channel_raw_samples": ["Con_Open Channel"],
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
    assert out.get("suggested_channel_id") == 202
    assert out.get("effective_channel_id") == 202
    msg = str(out.get("source_channel_resolution_message") or "")
    assert "Approved source channel token" in msg or "OPEN_CH" in msg


def test_plan_customer_provisional_channel_alias_conflict_not_ready() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=None)
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[201, 202])))
    job = MagicMock()
    job.source.id = 9
    prod_idx = MagicMock()
    cand = _cand(
        entity_type="customer_dealer_token",
        context={
            "source_customer_name_raw_samples": ["New Customer"],
            "dealer_group_account_raw": "DGNEW",
            "source_channel_evidence_norms": ["con_open channel"],
            "source_channel_raw_samples": ["Con_Open Channel"],
        },
    )
    with patch(
        "app.services.imports.dsi_resolution_plan.effective_dsi_customer_primary_for_resolution",
        return_value=("New Customer", []),
    ), patch(
        "app.services.imports.dsi_resolution_plan._resolve_customer",
        return_value=(None, ["nomatch"]),
    ):
        out = plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=10, default_channel_id=20)
    assert out["suggested_action"] == "create_provisional_customer"
    assert out["ready"] is True
    assert out.get("suggested_channel_id") is None
    assert out.get("used_global_fallback_channel") is True
    assert int(out.get("effective_channel_id") or 0) == 20
    det = str(out.get("source_channel_resolution_message") or "")
    assert "multiple approved channel" in det.lower() or "alias" in det.lower()


def test_merge_provisional_geo_conflict_ok_when_row_sets_region_channel() -> None:
    cand = _cand(
        entity_type="customer_dealer_token",
        context={"provisional_channel_conflict": True},
    )
    base = {
        "suggested_action": "create_provisional_customer",
        "suggested_target_id": None,
        "ready": False,
        "effective_region_id": 1,
        "effective_channel_id": 2,
    }
    m = merge_resolution_plan_row_for_apply(
        cand=cand,
        base=base,
        ov={"action": "create_provisional_customer", "region_id": 9, "channel_id": 8},
        default_region_id=10,
        default_channel_id=20,
        global_confirm_suspicious_distributor=False,
    )
    assert m["effective_ready"] is True
    assert m["effective_region_id"] == 9
    assert m["effective_channel_id"] == 8


def test_dsi_geo_channel_alias_source_id_prefers_candidate_definition() -> None:
    cand = MagicMock()
    cand.source_definition_id = 5
    job = MagicMock()
    job.source.id = 99
    assert dsi_geo_channel_alias_source_id(cand, job) == 5


def test_dsi_geo_channel_alias_source_id_falls_back_to_job() -> None:
    cand = MagicMock()
    cand.source_definition_id = None
    job = MagicMock()
    job.source.id = 88
    assert dsi_geo_channel_alias_source_id(cand, job) == 88


def test_dsi_geo_channel_alias_source_id_none_without_job_or_candidate_source() -> None:
    cand = MagicMock()
    cand.source_definition_id = None
    assert dsi_geo_channel_alias_source_id(cand, None) is None


def test_derive_effective_passes_candidate_source_definition_to_geo_resolution() -> None:
    sess = MagicMock()
    cand = _cand(source_definition_id=42, context={})
    job = MagicMock()
    job.source.id = 99
    captured: dict[str, int | None] = {}

    def fake_resolve(session, ctx, *, source_definition_id=None):
        captured["source_definition_id"] = source_definition_id
        return {
            "source_region_resolved_id": None,
            "source_channel_resolved_id": None,
            "provisional_region_conflict": False,
            "provisional_channel_conflict": False,
            "source_region_resolution_detail": "missing_source_evidence",
            "source_channel_resolution_detail": "missing_source_evidence",
            "source_region_raw_token": None,
            "source_channel_raw_token": None,
        }

    with patch(
        "app.services.imports.dsi_resolution_plan._resolve_source_geo_from_ctx",
        side_effect=fake_resolve,
    ):
        derive_effective_provisional_customer_geo_sync(
            sess, cand, default_region_id=None, default_channel_id=None, import_job=job
        )
    assert captured.get("source_definition_id") == 42


def test_derive_effective_falls_back_to_job_source_for_geo_resolution() -> None:
    sess = MagicMock()
    cand = _cand(source_definition_id=None, context={})
    job = MagicMock()
    job.source.id = 77
    captured: dict[str, int | None] = {}

    def fake_resolve(session, ctx, *, source_definition_id=None):
        captured["source_definition_id"] = source_definition_id
        return {
            "source_region_resolved_id": None,
            "source_channel_resolved_id": None,
            "provisional_region_conflict": False,
            "provisional_channel_conflict": False,
            "source_region_resolution_detail": "missing_source_evidence",
            "source_channel_resolution_detail": "missing_source_evidence",
            "source_region_raw_token": None,
            "source_channel_raw_token": None,
        }

    with patch(
        "app.services.imports.dsi_resolution_plan._resolve_source_geo_from_ctx",
        side_effect=fake_resolve,
    ):
        derive_effective_provisional_customer_geo_sync(
            sess, cand, default_region_id=None, default_channel_id=None, import_job=job
        )
    assert captured.get("source_definition_id") == 77


def test_resolve_dim_channel_duplicate_approved_alias_same_channel_dedupes() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(return_value=None)
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[303, 303])))
    cid, reason = _resolve_dim_channel_from_source(sess, "Con_Open Channel", source_definition_id=9)
    assert cid == 303
    assert reason == "source_channel_token_alias"


def test_channel_source_token_alias_registered_in_sqlalchemy_metadata() -> None:
    from app.db.base import Base

    assert "channel_source_token_alias" in Base.metadata.tables
