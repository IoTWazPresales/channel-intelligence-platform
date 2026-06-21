"""ProductResolutionIndex must hold detached plain rows — never Session-bound ORM instances."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.db.session_sync import SessionLocal
from app.services.imports import product_resolution_index_cache as cache_mod
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    ProductResolutionProductRow,
    _product_resolution_row_from_dim,
    _resolve_product,
)


def _sample_row(pid: int = 1, *, sku: str = "sku-main") -> ProductResolutionProductRow:
    return ProductResolutionProductRow(
        id=pid,
        sku=sku,
        part_number=None,
        sales_model_name="model-x",
        model_name=None,
        marketing_name=None,
        ean=None,
        upc=None,
        is_active=True,
        lifecycle_status=None,
        launch_date=None,
        retired_date=None,
    )


def test_narrow_load_snapshots_products_to_plain_rows() -> None:
    cache_mod.invalidate_product_resolution_index_cache()
    orm = SimpleNamespace(
        id=1,
        sku="SKU-MAIN",
        part_number=None,
        sales_model_name="MODEL-X",
        model_name=None,
        marketing_name=None,
        ean=None,
        upc=None,
        is_active=True,
        lifecycle_status=None,
        launch_date=None,
        retired_date=None,
    )

    class _Q:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

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

    db = _S([orm], [])
    idx = cache_mod._load_product_resolution_index_narrow(db)  # type: ignore[arg-type]
    row = idx.products_by_id[1]
    assert isinstance(row, ProductResolutionProductRow)
    assert row.sku == "SKU-MAIN"


def test_product_resolution_index_survives_session_close_without_db_access(monkeypatch) -> None:
    row = _sample_row()
    idx = ProductResolutionIndex(
        sku_to_id={"sku-main": 1},
        part_number_to_ids={},
        sales_model_name_to_ids={"model-x": (1,)},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        products_by_id={1: row},
        steward_alias_by_key={},
    )
    with SessionLocal() as db:
        db.commit()
        db.expunge_all()

        def _fail_db(*_args, **_kwargs):
            raise AssertionError("index access must not query DB after session close")

        monkeypatch.setattr(db, "execute", _fail_db)
        monkeypatch.setattr(db, "scalar", _fail_db)
        monkeypatch.setattr(db, "scalars", _fail_db)

        pid, err, tag, ev = _resolve_product("sku-main", idx, date(2024, 1, 15))
        assert pid == 1
        assert err is None
        assert tag == "product_resolved_sku"
        assert ev is None


def test_row_from_dim_preserves_eligibility_semantics() -> None:
    """ORM snapshot row must match live DimProduct for eligibility checks."""
    from app.services.imports.distributor_sales_inventory import _product_eligible_for_dsi_auto

    orm = SimpleNamespace(
        id=7,
        sku="S7",
        part_number=None,
        sales_model_name=None,
        model_name=None,
        marketing_name=None,
        ean=None,
        upc=None,
        is_active=False,
        lifecycle_status="retired",
        launch_date=date(2020, 1, 1),
        retired_date=date(2021, 1, 1),
    )
    plain = _product_resolution_row_from_dim(orm)
    ev = date(2021, 6, 1)
    assert _product_eligible_for_dsi_auto(orm, ev) == _product_eligible_for_dsi_auto(plain, ev)


def test_process_cache_returns_detached_index(monkeypatch) -> None:
    cache_mod.invalidate_product_resolution_index_cache()
    row = _sample_row()
    idx = ProductResolutionIndex(
        sku_to_id={"sku-main": 1},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        products_by_id={1: row},
        steward_alias_by_key={},
    )
    db = MagicMock()
    with patch.object(cache_mod, "_load_product_resolution_index_narrow", return_value=idx):
        loaded = cache_mod.get_product_resolution_index(db)
    assert isinstance(loaded.products_by_id[1], ProductResolutionProductRow)
