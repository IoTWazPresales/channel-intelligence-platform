"""Unit tests for DSI tiered product resolution (no database)."""

from __future__ import annotations

from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _load_product_resolution_index,
    _resolve_product,
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
) -> ProductResolutionIndex:
    return ProductResolutionIndex(
        sku_to_id=sku_to_id or {},
        part_number_to_ids=part_number_to_ids or {},
        sales_model_name_to_ids=sales_model_name_to_ids or {},
        model_name_to_ids=model_name_to_ids or {},
        marketing_name_to_ids=marketing_name_to_ids or {},
        ean_to_ids=ean_to_ids or {},
        upc_to_ids=upc_to_ids or {},
        alias_value_to_ids=alias_value_to_ids or {},
    )


def test_resolve_by_sku_wins_over_sales_model() -> None:
    idx = _idx(
        sku_to_id={"x-1": 10},
        sales_model_name_to_ids={"x-1": (99,)},
    )
    pid, err, tag = _resolve_product("X-1", idx)
    assert err is None and pid == 10 and tag == "product_resolved_sku"


def test_resolve_by_sales_model_when_no_sku_match() -> None:
    token = "e510ka-c42b1w"
    idx = _idx(
        sku_to_id={"other-sku": 1},
        sales_model_name_to_ids={token: (42,)},
    )
    pid, err, tag = _resolve_product("E510KA-C42B1W", idx)
    assert err is None and pid == 42 and tag == "product_resolved_sales_model_name"


def test_resolve_part_number_tier_before_sales_model() -> None:
    key = "pn-777"
    idx = _idx(
        part_number_to_ids={key: (5,)},
        sales_model_name_to_ids={key: (6,)},
    )
    pid, err, tag = _resolve_product("PN-777", idx)
    assert err is None and pid == 5 and tag == "product_resolved_part_number"


def test_ambiguous_same_tier_returns_error() -> None:
    idx = _idx(sales_model_name_to_ids={"dup": (1, 2)})
    pid, err, tag = _resolve_product("dup", idx)
    assert pid is None and err == "ambiguous_product_match" and tag is None


def test_ambiguous_alias_returns_distinct_code() -> None:
    idx = _idx(alias_value_to_ids={"alias-dup": (7, 8)})
    pid, err, tag = _resolve_product("ALIAS-DUP", idx)
    assert pid is None and err == "ambiguous_product_alias" and tag is None


def test_alias_tier_used_after_dim_fields() -> None:
    idx = _idx(
        sales_model_name_to_ids={},  # no hit
        alias_value_to_ids={"only-alias": (100,)},
    )
    pid, err, tag = _resolve_product("only-alias", idx)
    assert err is None and pid == 100 and tag == "product_resolved_alias"


def test_unresolved_when_no_match() -> None:
    pid, err, tag = _resolve_product("nope", _idx())
    assert pid is None and err == "unresolved_product" and tag is None


def test_missing_token() -> None:
    pid, err, tag = _resolve_product("   ", _idx(sku_to_id={"a": 1}))
    assert pid is None and err == "missing_product_token"


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
