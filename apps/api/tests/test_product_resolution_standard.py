"""Tests for shared single-match product resolution tiers (INT-04, non-DSI)."""

from __future__ import annotations

from app.services.imports.distributor_sales_inventory import ProductResolutionIndex
from app.services.imports.product_resolution_standard import resolve_product_id_single_match


def _idx(**kwargs) -> ProductResolutionIndex:
    base = dict(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        steward_alias_by_key={},
        products_by_id={},
    )
    base.update(kwargs)
    return ProductResolutionIndex(**base)


def test_standard_order_sku_before_ean() -> None:
    idx = _idx(sku_to_id={"abc": 1}, ean_to_ids={"abc": (2, 3)})
    assert resolve_product_id_single_match(idx, "abc") == 1


def test_standard_order_ean_before_sales_model() -> None:
    idx = _idx(ean_to_ids={"abc": (5,)}, sales_model_name_to_ids={"abc": (9, 10)})
    assert resolve_product_id_single_match(idx, "abc") == 5


def test_standard_ambiguous_tier_returns_none() -> None:
    idx = _idx(ean_to_ids={"abc": (5, 6)})
    assert resolve_product_id_single_match(idx, "abc") is None
