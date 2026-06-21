"""Unit tests for ProductResolutionIndex process cache."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.imports import product_resolution_index_cache as cache_mod


def test_cache_returns_same_index_within_ttl() -> None:
    cache_mod.invalidate_product_resolution_index_cache()
    idx = SimpleNamespace(sku_to_id={"a": 1})
    db = MagicMock()

    with patch.object(cache_mod, "_load_product_resolution_index_narrow", return_value=idx) as load:
        first = cache_mod.get_product_resolution_index(db)
        second = cache_mod.get_product_resolution_index(db)

    assert first is second
    load.assert_called_once()


def test_invalidate_forces_reload() -> None:
    cache_mod.invalidate_product_resolution_index_cache()
    db = MagicMock()
    calls = [SimpleNamespace(sku_to_id={"a": 1}), SimpleNamespace(sku_to_id={"b": 2})]

    with patch.object(cache_mod, "_load_product_resolution_index_narrow", side_effect=calls):
        first = cache_mod.get_product_resolution_index(db)
        cache_mod.invalidate_product_resolution_index_cache()
        second = cache_mod.get_product_resolution_index(db)

    assert first is not second
    assert first.sku_to_id == {"a": 1}
    assert second.sku_to_id == {"b": 2}
