"""Lineup customer resolution via approved CustomerSourceTokenAlias (no DB)."""

from types import SimpleNamespace

from app.services.commercial_planner.lineup_customer_alias_resolution import (
    resolve_lineup_customer_id_from_token,
)
from app.services.imports.shipment_evidence_resolution_plan import (
    build_unique_approved_customer_alias_id_by_token,
)


def test_build_unique_alias_map_skips_ambiguous_tokens():
    rows = [
        ("ic", 12, None),
        ("ic", 12, 1),
        ("lewis", 5, None),
        ("lewis", 9, None),
        ("sample", 80, None),
    ]
    m = build_unique_approved_customer_alias_id_by_token(rows)
    assert m == {"ic": 12, "sample": 80}
    assert "lewis" not in m


def test_resolve_lineup_customer_prefers_name_code_then_alias():
    cust = SimpleNamespace(id=12, name="Incredible Connection", code="TMP-CUST-X")
    customer_map = {"incredible connection": cust}
    customers_by_id = {12: cust}
    alias_map = {"ic": 12}

    assert (
        resolve_lineup_customer_id_from_token(
            "Incredible Connection",
            customer_map=customer_map,
            customer_alias_map=alias_map,
            customers_by_id=customers_by_id,
        )
        == 12
    )
    assert (
        resolve_lineup_customer_id_from_token(
            "IC",
            customer_map={},
            customer_alias_map=alias_map,
            customers_by_id=customers_by_id,
        )
        == 12
    )
    assert (
        resolve_lineup_customer_id_from_token(
            "unknown",
            customer_map={},
            customer_alias_map=alias_map,
            customers_by_id=customers_by_id,
        )
        is None
    )


def test_resolve_lineup_customer_alias_requires_dim_row_present():
    alias_map = {"ic": 12}
    assert (
        resolve_lineup_customer_id_from_token(
            "IC",
            customer_map={},
            customer_alias_map=alias_map,
            customers_by_id={},
        )
        == 12
    )
