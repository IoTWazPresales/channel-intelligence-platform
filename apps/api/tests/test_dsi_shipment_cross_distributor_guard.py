"""Cross-distributor shipment disambiguation must not auto-resolve DSI product rows."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.services.imports.distributor_sales_inventory import _shipment_disambiguate_product_id


def test_cross_distributor_scope_does_not_auto_resolve() -> None:
    cache = MagicMock()
    cache.product_corroboration.return_value = {
        "distinct_resolved_product_ids": [42],
        "distinct_ids_scope": "cross_distributor",
        "match_count": 3,
    }
    pick, scope = _shipment_disambiguate_product_id(
        None,
        distributor_id=21,
        evidence_date=date(2025, 6, 1),
        raw="FA506",
        candidate_ids=[42, 99],
        corr_cache=cache,
    )
    assert pick is None
    assert scope is None


def test_distributor_specific_scope_still_resolves() -> None:
    cache = MagicMock()
    cache.product_corroboration.return_value = {
        "distinct_resolved_product_ids": [42],
        "distinct_ids_scope": "distributor_specific",
        "match_count": 2,
    }
    pick, scope = _shipment_disambiguate_product_id(
        None,
        distributor_id=21,
        evidence_date=date(2025, 6, 1),
        raw="FA506",
        candidate_ids=[42, 99],
        corr_cache=cache,
    )
    assert pick == 42
    assert scope == "distributor_specific"
