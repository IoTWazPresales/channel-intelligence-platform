"""Step 2 (N-0122): promotion families, so the planner never mixes customer sell-through with sell-out.

Warren (standing rule): "Promotions are sell-throughs. Sell-out is distributor (disti) to customer. They must
not be mixed. The promotion planner shows customer promotions, never sell-out."
Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is still valuable but not here."
No database: pure vocabulary checks plus the meta endpoint and the compiled list filter.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from app.api.v1.endpoints import cpor_cases as ep
from app.main import app
from app.models.cpor import CporCase
from app.models.dimensions import DimCustomer
from app.services.cpor import promo_plan_builder
from app.services.cpor.promotion_type_vocab import (
    CPOR_PROMOTION_TYPES,
    CUSTOMER_SELL_THROUGH,
    DEFAULT_CUSTOMER_PROMOTION_TYPE,
    DISTRIBUTOR_SELL_OUT,
    PROMOTION_FAMILIES,
    promotion_family,
    promotion_family_types,
)
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


def test_every_family_type_is_a_stored_cpor_type():
    for types in PROMOTION_FAMILIES.values():
        for t in types:
            assert t in CPOR_PROMOTION_TYPES


def test_the_two_families_do_not_share_a_type():
    st = set(promotion_family_types(CUSTOMER_SELL_THROUGH))
    so = set(promotion_family_types(DISTRIBUTOR_SELL_OUT))
    assert st and so
    assert not st & so


def test_family_is_exact_after_case_and_whitespace_only():
    assert promotion_family("Sell-Through PP") == CUSTOMER_SELL_THROUGH
    assert promotion_family("  sell-through   pp ") == CUSTOMER_SELL_THROUGH
    assert promotion_family("Sell out PP") == DISTRIBUTOR_SELL_OUT
    assert promotion_family("SELL OUT PP") == DISTRIBUTOR_SELL_OUT
    # No substring or punctuation folding: a near miss belongs to no family.
    assert promotion_family("Sell Through PP") is None
    assert promotion_family("Sell out") is None
    assert promotion_family("PP") is None
    assert promotion_family(None) is None
    assert promotion_family("") is None


def test_stock_pp_is_in_no_family_by_default():
    # ASSUMPTION B3: Stock PP (In-Direct) stays off the planner until Warren includes it.
    assert promotion_family("Stock PP (In-Direct)") is None


def test_unknown_family_raises():
    with pytest.raises(KeyError):
        promotion_family_types("sell_everything")


def test_new_plan_defaults_are_the_first_customer_sell_through_type():
    assert DEFAULT_CUSTOMER_PROMOTION_TYPE == promotion_family_types(CUSTOMER_SELL_THROUGH)[0]
    assert promo_plan_builder.DEFAULT_PROPOSAL_PROMOTION_TYPE == DEFAULT_CUSTOMER_PROMOTION_TYPE
    assert promotion_family(promo_plan_builder.DEFAULT_PROPOSAL_PROMOTION_TYPE) == CUSTOMER_SELL_THROUGH


def test_meta_promotion_types_by_family():
    body = ep.promotion_types(family=CUSTOMER_SELL_THROUGH)
    assert body["promotion_types"] == list(promotion_family_types(CUSTOMER_SELL_THROUGH))
    assert "Sell out PP" not in body["promotion_types"]
    assert body["family"] == CUSTOMER_SELL_THROUGH


def test_meta_promotion_types_without_family_is_unchanged():
    assert ep.promotion_types()["promotion_types"] == sorted(CPOR_PROMOTION_TYPES)
    assert ep.promotion_types(family=None)["promotion_types"] == sorted(CPOR_PROMOTION_TYPES)


def test_meta_promotion_types_unknown_family_is_400():
    with pytest.raises(HTTPException) as exc:
        ep.promotion_types(family="nope")
    assert exc.value.status_code == 400


def test_meta_promotion_types_route_declares_the_family_param():
    route = next(r for r in app.routes if getattr(r, "path", "") == "/api/v1/cpor/meta/promotion-types")
    assert "family" in {p.name for p in route.dependant.query_params}


def _filtered_sql(**kw: Any) -> str:
    base = select(CporCase.id).join(DimCustomer, DimCustomer.id == CporCase.customer_id)
    args: dict[str, Any] = dict(
        status=None,
        customer_id=None,
        distributor_id=None,
        product_id=None,
        business_unit=None,
        window_from=None,
        window_to=None,
        test_data=None,
        q=None,
        evidence_basis=None,
    )
    args.update(kw)
    stmt = ep._apply_case_filters(None, base, **args)
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return " ".join(sql.split())


def test_family_filter_reaches_the_statement():
    sql = _filtered_sql(promotion_family=CUSTOMER_SELL_THROUGH)
    assert "cpor_case.promotion_type IN ('Sell-Through PP')" in sql
    assert "Sell out PP" not in sql


def test_open_only_filter_reaches_the_statement():
    sql = _filtered_sql(open_only=True, today=date(2026, 11, 26))
    assert "cpor_case.status IN ('draft', 'proposed', 'approved', 'active')" in sql
    assert "cpor_case.superseded_by_case_id IS NULL" in sql
    assert "cpor_case.window_end >= '2026-11-26'" in sql


def test_no_family_and_no_open_only_add_nothing():
    sql = _filtered_sql()
    assert "promotion_type" not in sql
    assert "superseded_by_case_id" not in sql


def test_unknown_family_on_the_list_filter_is_400():
    with pytest.raises(HTTPException) as exc:
        _filtered_sql(promotion_family="nope")
    assert exc.value.status_code == 400
