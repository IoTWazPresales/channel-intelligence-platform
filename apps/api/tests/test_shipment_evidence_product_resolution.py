"""Shipment evidence product resolution: SKU launch-window anchor (no database)."""

from __future__ import annotations

from datetime import date

from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    ProductResolutionProductRow,
    _product_eligible_for_dsi_auto,
    _product_eligible_for_shipment_sku_item_code_anchor,
    _resolve_product,
)
from app.services.imports.shipment_evidence_import import resolve_product_for_evidence


def _p(
    id_: int,
    *,
    sku: str = "SKU",
    sales_model_name: str | None = None,
    is_active: bool = True,
    lifecycle_status: str | None = None,
    launch_date: date | None = None,
    retired_date: date | None = None,
) -> ProductResolutionProductRow:
    return ProductResolutionProductRow(
        id=id_,
        sku=sku,
        part_number=None,
        sales_model_name=sales_model_name,
        model_name=None,
        marketing_name=None,
        ean=None,
        upc=None,
        is_active=is_active,
        lifecycle_status=lifecycle_status,
        launch_date=launch_date,
        retired_date=retired_date,
    )


def _idx(*, sku_to_id: dict[str, int], products_by_id: dict[int, ProductResolutionProductRow]) -> ProductResolutionIndex:
    return ProductResolutionIndex(
        sku_to_id=sku_to_id,
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        products_by_id=products_by_id,
        steward_alias_by_key={},
    )


def test_discarded_sku_in_launch_window_resolves_unique() -> None:
    sku = "DISC-SKU-1"
    ev = date(2020, 6, 15)
    idx = _idx(
        sku_to_id={sku.lower(): 42},
        products_by_id={
            42: _p(
                42,
                sku=sku,
                is_active=True,
                lifecycle_status="Discarded",
                launch_date=date(2020, 1, 1),
                retired_date=date(2021, 12, 31),
            ),
        },
    )
    pid, status, token, detail = resolve_product_for_evidence(
        idx,
        item_code=sku,
        ean_code=None,
        upc_code=None,
        sales_model_name=None,
        evidence_date=ev,
    )
    assert pid == 42
    assert status == "resolved_unique"
    assert token == sku
    assert _product_eligible_for_dsi_auto(idx.products_by_id[42], ev) is False
    assert _product_eligible_for_shipment_sku_item_code_anchor(idx.products_by_id[42], ev) is True


def test_discarded_sku_outside_launch_window_stays_inactive_only() -> None:
    sku = "DISC-SKU-2"
    ev = date(2022, 6, 15)
    idx = _idx(
        sku_to_id={sku.lower(): 7},
        products_by_id={
            7: _p(
                7,
                sku=sku,
                is_active=True,
                lifecycle_status="Discarded",
                launch_date=date(2020, 1, 1),
                retired_date=date(2021, 12, 31),
            ),
        },
    )
    pid, status, token, detail = resolve_product_for_evidence(
        idx,
        item_code=sku,
        ean_code=None,
        upc_code=None,
        sales_model_name=None,
        evidence_date=ev,
    )
    assert pid is None
    assert status == "inactive_only"
    assert token == sku
    assert detail == "unresolved_product_inactive_only"


def test_sku_anchor_does_not_loosen_sales_model_tier() -> None:
    token = "sm-discarded"
    ev = date(2020, 6, 15)
    idx = ProductResolutionIndex(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={token: (99,)},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        products_by_id={
            99: _p(
                99,
                sku="ONLY-SM",
                sales_model_name=token,
                is_active=True,
                lifecycle_status="Discarded",
                launch_date=date(2020, 1, 1),
                retired_date=date(2021, 12, 31),
            ),
        },
        steward_alias_by_key={},
    )
    pid, status, _token, detail = resolve_product_for_evidence(
        idx,
        item_code=None,
        ean_code=None,
        upc_code=None,
        sales_model_name=token,
        evidence_date=ev,
    )
    assert pid is None
    assert status == "inactive_only"
    assert detail == "unresolved_product_inactive_only"


def test_resolve_product_sku_anchor_default_off_unchanged_for_dsi_path() -> None:
    sku = "ANCHOR-OFF"
    ev = date(2020, 6, 15)
    idx = _idx(
        sku_to_id={sku.lower(): 3},
        products_by_id={
            3: _p(
                3,
                sku=sku,
                lifecycle_status="Discarded",
                launch_date=date(2020, 1, 1),
                retired_date=date(2021, 12, 31),
            ),
        },
    )
    pid, err, tag, ev_out = _resolve_product(sku, idx, ev)
    assert pid is None and err == "unresolved_product_inactive_only" and tag is None
    assert ev_out is not None
