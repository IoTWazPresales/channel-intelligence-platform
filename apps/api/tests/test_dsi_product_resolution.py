"""Unit tests for DSI tiered lifecycle-aware product resolution (no database)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _load_product_resolution_index,
    _product_eligible_for_dsi_auto,
    _resolve_product,
)


def _p(
    id_: int,
    *,
    sku: str = "SKU",
    part_number: str | None = None,
    sales_model_name: str | None = None,
    is_active: bool = True,
    lifecycle_status: str | None = None,
    launch_date: date | None = None,
    retired_date: date | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        sku=sku,
        part_number=part_number,
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


def _idx(
    *,
    sku_to_id: dict[str, int] | None = None,
    part_number_to_ids: dict[str, tuple[int, ...]] | None = None,
    sales_model_name_to_ids: dict[str, tuple[int, ...]] | None = None,
    model_name_to_ids: dict[str, tuple[int, ...]] | None = None,
    marketing_name_to_ids: dict[str, tuple[int, ...]] | None = None,
    ean_to_ids: dict[str, tuple[int, ...]] | None = None,
    upc_to_ids: dict[str, tuple[int, ...]] | None = None,
    alias_value_to_ids: dict[str, tuple[int, ...]] | None = None,
    products_by_id: dict[int, SimpleNamespace] | None = None,
) -> ProductResolutionIndex:
    sku_to_id = sku_to_id or {}
    part_number_to_ids = part_number_to_ids or {}
    sales_model_name_to_ids = sales_model_name_to_ids or {}
    model_name_to_ids = model_name_to_ids or {}
    marketing_name_to_ids = marketing_name_to_ids or {}
    ean_to_ids = ean_to_ids or {}
    upc_to_ids = upc_to_ids or {}
    alias_value_to_ids = alias_value_to_ids or {}
    if products_by_id is None:
        ids: set[int] = set()
        for v in sku_to_id.values():
            ids.add(int(v))
        for m in (
            part_number_to_ids,
            sales_model_name_to_ids,
            model_name_to_ids,
            marketing_name_to_ids,
            ean_to_ids,
            upc_to_ids,
            alias_value_to_ids,
        ):
            for t in m.values():
                ids.update(int(x) for x in t)
        products_by_id = {i: _p(i, sku=f"SKU-{i}") for i in ids}
    return ProductResolutionIndex(
        sku_to_id=sku_to_id,
        part_number_to_ids=part_number_to_ids,
        sales_model_name_to_ids=sales_model_name_to_ids,
        model_name_to_ids=model_name_to_ids,
        marketing_name_to_ids=marketing_name_to_ids,
        ean_to_ids=ean_to_ids,
        upc_to_ids=upc_to_ids,
        alias_value_to_ids=alias_value_to_ids,
        products_by_id=products_by_id,  # type: ignore[arg-type]
    )


def test_resolve_by_sku_wins_over_sales_model() -> None:
    idx = _idx(
        sku_to_id={"x-1": 10},
        sales_model_name_to_ids={"x-1": (99,)},
        products_by_id={10: _p(10, sku="X-1"), 99: _p(99, sku="OTHER", sales_model_name="X-1")},
    )
    pid, err, tag, ev = _resolve_product("X-1", idx, None)
    assert ev is None
    assert err is None and pid == 10 and tag == "product_resolved_sku"


def test_resolve_by_sales_model_when_no_sku_match() -> None:
    token = "e510ka-c42b1w"
    idx = _idx(
        sku_to_id={"other-sku": 1},
        sales_model_name_to_ids={token: (42,)},
        products_by_id={1: _p(1, sku="other-sku"), 42: _p(42, sku="INT-SKU", sales_model_name="E510KA-C42B1W")},
    )
    pid, err, tag, ev = _resolve_product("E510KA-C42B1W", idx, None)
    assert ev is None
    assert err is None and pid == 42 and tag == "product_resolved_sales_model_name"


def test_resolve_part_number_tier_before_sales_model() -> None:
    key = "pn-777"
    idx = _idx(
        part_number_to_ids={key: (5,)},
        sales_model_name_to_ids={key: (6,)},
        products_by_id={
            5: _p(5, sku="A", part_number="PN-777"),
            6: _p(6, sku="B", sales_model_name="PN-777"),
        },
    )
    pid, err, tag, ev = _resolve_product("PN-777", idx, None)
    assert ev is None
    assert err is None and pid == 5 and tag == "product_resolved_part_number"


def test_ambiguous_two_active_same_tier() -> None:
    idx = _idx(
        sales_model_name_to_ids={"dup": (1, 2)},
        products_by_id={1: _p(1, sku="S1", sales_model_name="dup"), 2: _p(2, sku="S2", sales_model_name="dup")},
    )
    pid, err, tag, ev = _resolve_product("dup", idx, None)
    assert pid is None and err == "ambiguous_product_match" and tag is None
    assert ev is not None and ev.ambiguous_eligible is not None
    assert set(ev.ambiguous_eligible.get("product_ids", [])) == {1, 2}


def test_active_wins_when_duplicate_sales_model_one_inactive() -> None:
    idx = _idx(
        sales_model_name_to_ids={"smx": (1, 2)},
        products_by_id={
            1: _p(1, sku="ACTIVE-SKU", sales_model_name="smx", is_active=True),
            2: _p(2, sku="OLD-SKU", sales_model_name="smx", is_active=False),
        },
    )
    pid, err, tag, ev = _resolve_product("smx", idx, None)
    assert ev is None and err is None and pid == 1 and tag == "product_resolved_sales_model_name"


def test_only_inactive_matches_unresolved_with_evidence() -> None:
    idx = _idx(
        sales_model_name_to_ids={"smx": (1, 2)},
        products_by_id={
            1: _p(1, sku="A", sales_model_name="smx", is_active=False),
            2: _p(2, sku="B", sales_model_name="smx", lifecycle_status="retired"),
        },
    )
    pid, err, tag, ev = _resolve_product("smx", idx, None)
    assert pid is None and err == "unresolved_product_inactive_only" and tag is None
    assert ev is not None and len(ev.inactive_hits) >= 1


def test_inactive_sales_model_but_resolves_via_alias_active() -> None:
    idx = _idx(
        sales_model_name_to_ids={"tok": (1, 2)},
        alias_value_to_ids={"tok": (10,)},
        products_by_id={
            1: _p(1, sku="A", sales_model_name="tok", is_active=False),
            2: _p(2, sku="B", sales_model_name="tok", is_active=False),
            10: _p(10, sku="ALIAS-SKU", is_active=True),
        },
    )
    pid, err, tag, ev = _resolve_product("tok", idx, None)
    assert ev is None
    assert err is None and pid == 10 and tag == "product_resolved_alias"


def test_ambiguous_alias_returns_distinct_code() -> None:
    idx = _idx(
        alias_value_to_ids={"alias-dup": (7, 8)},
        products_by_id={7: _p(7, sku="S7"), 8: _p(8, sku="S8")},
    )
    pid, err, tag, ev = _resolve_product("ALIAS-DUP", idx, None)
    assert pid is None and err == "ambiguous_product_alias" and tag is None
    assert ev is not None and ev.ambiguous_eligible is not None


def test_unresolved_when_no_match() -> None:
    pid, err, tag, ev = _resolve_product("nope", _idx())
    assert pid is None and err == "unresolved_product" and tag is None
    assert ev is None


def test_missing_token() -> None:
    pid, err, tag, ev = _resolve_product("   ", _idx(sku_to_id={"a": 1}))
    assert pid is None and err == "missing_product_token"
    assert ev is None


def test_retired_before_evidence_date_ineligible() -> None:
    p = _p(1, sku="S", sales_model_name="smz", retired_date=date(2020, 1, 1))
    assert _product_eligible_for_dsi_auto(p, date(2021, 6, 1)) is False
    assert _product_eligible_for_dsi_auto(p, date(2019, 6, 1)) is True


def test_load_product_resolution_index_builds_maps() -> None:
    """Smoke: index builder maps ORM rows into lookup structures (session mocked)."""

    class _P:
        def __init__(self, id_: int, sku: str, sales_model_name: str | None = None):
            self.id = id_
            self.sku = sku
            self.part_number = None
            self.sales_model_name = sales_model_name
            self.model_name = None
            self.marketing_name = None
            self.ean = None
            self.upc = None
            self.is_active = True
            self.lifecycle_status = None
            self.launch_date = None
            self.retired_date = None

    class _A:
        def __init__(self, product_id: int, alias_value: str):
            self.product_id = product_id
            self.alias_value = alias_value

    class _Q:
        def __init__(self, items):
            self._items = items

        def all(self):
            return list(self._items)

    class _S:
        def __init__(self, products, aliases):
            self._products = products
            self._aliases = aliases
            self._call = 0

        def scalars(self, _stmt):
            self._call += 1
            if self._call == 1:
                return _Q(self._products)
            return _Q(self._aliases)

    products = [_P(1, "SKU-MAIN", sales_model_name="MODEL-X")]
    aliases = [_A(1, "DISTRO-CODE-Z")]
    idx = _load_product_resolution_index(_S(products, aliases))  # type: ignore[arg-type]
    assert idx.sku_to_id["sku-main"] == 1
    assert idx.sales_model_name_to_ids["model-x"] == (1,)
    assert idx.alias_value_to_ids["distro-code-z"] == (1,)
    assert idx.products_by_id[1].sku == "SKU-MAIN"
