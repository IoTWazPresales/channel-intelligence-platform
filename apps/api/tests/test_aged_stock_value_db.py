"""BACKLOG-254: the aged-stock money value reads the real cost source on cip_test (rolled back).

Cost source = ``customer_soh_check`` -> ``soh_unit_cost``: the customer's reported unit MAC,
else unit cost, ex-VAT, from ``fact_customer_sellthrough`` (the SOH check and CPOR tier-1 cost).
Fictional data; the aged lines are passed in, so no store/DC view is needed.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.store_dc.stock_actions import (
    _unit_cost_lookup,
    summarise_aged_value,
    value_aged_lines,
)
from sqlalchemy import text

AS_OF = date(2026, 11, 19)
PERIOD = date(2026, 11, 9)


@pytest.fixture
def world():
    tag = uuid4().hex[:10]
    tenant = f"av-{tag}"
    session = SessionLocal()
    try:
        assert session.execute(text("select current_database()")).scalar_one() == "cip_test"
        session.execute(
            text("INSERT INTO tenant (id, name) VALUES (:id, 'aged value')"), {"id": tenant}
        )
        cust = DimCustomer(tenant_id=tenant, code=f"AV-{tag}", name=f"Cust {tag}")
        products = [
            DimProduct(tenant_id=tenant, sku=f"AV-{tag}-{i}", name=f"P{i}") for i in range(5)
        ]
        session.add_all([cust, *products])
        session.flush()
        yield {"tag": tag, "tenant": tenant, "session": session, "cust": cust, "products": products}
    finally:
        session.rollback()
        session.close()


def _fact(w, product, n, *, soh, mac=None, cost=None, vat="ex_vat", period=PERIOD):
    w["session"].add(
        FactCustomerSellthrough(
            source_key=f"av-{w['tag']}-{n}",
            tenant_id=w["tenant"],
            customer_id=w["cust"].id,
            product_id=product.id,
            period_start_date=period,
            period_type="week",
            units_sold=0,
            reported_soh=soh,
            unit_mac=mac,
            unit_cost=cost,
            vat_basis=vat,
        )
    )
    w["session"].flush()


def _line(w, product, soh):
    return {
        "customer_id": w["cust"].id,
        "product_id": product.id,
        "stock_on_hand": soh,
        "suggestion_executed": False,
        "executed_actions": [],
    }


def test_mac_is_preferred_then_unit_cost_and_incl_vat_is_taken_ex_vat(world):
    w = world
    p_mac, p_cost, p_incl = w["products"][:3]
    _fact(w, p_mac, 1, soh=10, mac=20, cost=99)  # MAC wins over unit cost
    _fact(w, p_cost, 2, soh=10, cost=5)  # no MAC: unit cost
    _fact(w, p_incl, 3, soh=10, mac=11.5, vat="incl_vat")  # 11.50 incl VAT = 10.00 ex VAT
    lookup = _unit_cost_lookup(w["session"], tenant_id=w["tenant"], as_of=AS_OF)
    lines = value_aged_lines([_line(w, p_mac, 4), _line(w, p_cost, 2), _line(w, p_incl, 3)], lookup)
    assert [(ln["unit_cost_field"], ln["unit_cost"], ln["stock_value"]) for ln in lines] == [
        ("unit_mac", 20.0, 80.0),
        ("unit_cost", 5.0, 10.0),
        ("unit_mac", 10.0, 30.0),
    ]


def test_no_cost_row_or_unknown_vat_basis_means_no_cost_never_zero(world):
    w = world
    p_none, p_unknown, p_priced = w["products"][:3]
    _fact(w, p_none, 1, soh=7)  # stock reported, no cost field
    _fact(w, p_unknown, 2, soh=7, mac=9, vat=None)  # cost with an unknown VAT basis is left out
    _fact(w, p_priced, 3, soh=7, mac=3)
    lookup = _unit_cost_lookup(w["session"], tenant_id=w["tenant"], as_of=AS_OF)
    lines = value_aged_lines(
        [
            _line(w, p_none, 7),
            _line(w, p_unknown, 7),
            _line(w, p_priced, 7),
            _line(w, w["products"][4], 2),
        ],
        lookup,
    )
    assert [ln["stock_value"] for ln in lines] == [None, None, 21.0, None]
    block = summarise_aged_value(lines)["unplanned"]
    assert (
        block["lines"] == 4 and block["lines_with_cost"] == 1 and block["lines_without_cost"] == 3
    )
    assert block["value"] == 21.0 and block["units_without_cost"] == 16.0


def test_a_cost_row_after_the_as_of_date_is_not_used(world):
    w = world
    p = w["products"][0]
    _fact(w, p, 1, soh=5, mac=4, period=date(2026, 12, 7))  # reported after AS_OF
    lookup = _unit_cost_lookup(w["session"], tenant_id=w["tenant"], as_of=AS_OF)
    [line] = value_aged_lines([_line(w, p, 5)], lookup)
    assert line["stock_value"] is None
