"""Unit tests for DSI product steward validation (no database)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.imports.dsi_product_steward import raw_product_token_for_dsi_candidate, validate_dsi_product_resolve


def _prod(
    pid: int,
    *,
    active: bool = True,
    lifecycle: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=pid,
        sku=f"SKU-{pid}",
        part_number=None,
        sales_model_name=None,
        model_name=None,
        marketing_name=None,
        ean=None,
        upc=None,
        is_active=active,
        lifecycle_status=lifecycle,
        launch_date=None,
        retired_date=None,
    )


def test_raw_token_prefers_override_then_samples() -> None:
    assert (
        raw_product_token_for_dsi_candidate(
            sample_raw_values=["A", "B"], normalized_key="z", raw_override="  OVR "
        )
        == "OVR"
    )
    assert (
        raw_product_token_for_dsi_candidate(sample_raw_values=["  first  "], normalized_key="z", raw_override=None)
        == "first"
    )
    assert raw_product_token_for_dsi_candidate(sample_raw_values=[], normalized_key="nk", raw_override=None) == "nk"


def test_ambiguous_requires_id_in_list() -> None:
    ctx = {"product_ambiguous_eligible": {"product_ids": [10, 20], "tier": "sales_model_name"}}
    validate_dsi_product_resolve(
        context=ctx,
        selected_product_id=10,
        selected_product=_prod(10),
        confirm_ineligible_product=False,
        audit_note=None,
    )
    with pytest.raises(ValueError, match="ambiguous"):
        validate_dsi_product_resolve(
            context=ctx,
            selected_product_id=99,
            selected_product=_prod(99),
            confirm_ineligible_product=False,
            audit_note=None,
        )


def test_inactive_product_requires_confirm_and_note() -> None:
    ctx: dict = {}
    p = _prod(5, active=False)
    with pytest.raises(ValueError, match="confirm_ineligible"):
        validate_dsi_product_resolve(
            context=ctx,
            selected_product_id=5,
            selected_product=p,
            confirm_ineligible_product=False,
            audit_note=None,
        )
    with pytest.raises(ValueError, match="audit_note"):
        validate_dsi_product_resolve(
            context=ctx,
            selected_product_id=5,
            selected_product=p,
            confirm_ineligible_product=True,
            audit_note="short",
        )
    validate_dsi_product_resolve(
        context=ctx,
        selected_product_id=5,
        selected_product=p,
        confirm_ineligible_product=True,
        audit_note="steward confirms historical use",
    )


def test_active_product_no_extra_confirm_even_if_context_ambiguous_cleared() -> None:
    ctx: dict = {}
    p = _prod(1, active=True)
    validate_dsi_product_resolve(
        context=ctx,
        selected_product_id=1,
        selected_product=p,
        confirm_ineligible_product=False,
        audit_note=None,
    )


def test_active_but_retired_lifecycle_requires_confirm_and_note() -> None:
    """Active flag alone does not override a clearly retired lifecycle string for DSI auto-eligibility."""
    ctx: dict = {}
    p = _prod(7, active=True, lifecycle="Retired")
    with pytest.raises(ValueError, match="confirm_ineligible"):
        validate_dsi_product_resolve(
            context=ctx,
            selected_product_id=7,
            selected_product=p,
            confirm_ineligible_product=False,
            audit_note=None,
        )
    validate_dsi_product_resolve(
        context=ctx,
        selected_product_id=7,
        selected_product=p,
        confirm_ineligible_product=True,
        audit_note="steward documents historical evidence",
    )


def test_ambiguous_with_empty_product_ids_rejects_selection() -> None:
    ctx = {"product_ambiguous_eligible": {"product_ids": [], "tier": "sales_model_name"}}
    with pytest.raises(ValueError, match="ambiguous"):
        validate_dsi_product_resolve(
            context=ctx,
            selected_product_id=1,
            selected_product=_prod(1),
            confirm_ineligible_product=False,
            audit_note=None,
        )
