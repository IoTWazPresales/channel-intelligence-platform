"""N-0049 / BACKLOG-135 — customer SOH check reads CST (mocked session; no DB writes)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.cpor.customer_soh_check import (
    SOURCE_TABLE,
    customer_soh_check,
    summarise_soh_rows,
)

AS_OF = date(2026, 9, 21)
WK = date(2026, 9, 14)


def _row(i, soh, unit_mac=None, unit_cost=None, vat="ex_vat"):
    return (i, WK, "weekly", soh, unit_mac, unit_cost, vat)


def _session(rows):
    session = MagicMock()
    res = MagicMock()
    res.all = MagicMock(return_value=rows)
    session.execute = MagicMock(return_value=res)
    return session


def test_source_is_cst_not_inventory_fact():
    session = _session([_row(1, Decimal("5"), unit_cost=Decimal("100"))])
    out = customer_soh_check(session, customer_id=1, product_id=2, as_of=AS_OF)
    assert out["source"] == SOURCE_TABLE == "fact_customer_sellthrough"
    sql = str(session.execute.call_args.args[0])
    assert "fact_customer_sellthrough" in sql
    assert "fact_inventory_customer" not in sql
    assert "reported_soh IS NOT NULL" in sql
    assert "max(fact_customer_sellthrough.period_start_date)" in sql
    assert out["soh_units"] == 5.0 and out["soh_unit_cost"] == 100.0
    assert out["vat_basis"] == "ex_vat"


def test_sites_summed_cost_soh_weighted_unit_mac_preferred():
    # Game-style: several sites in one week. unit_mac wins over unit_cost per row.
    rows = [
        _row(1, Decimal("10"), unit_mac=Decimal("200"), unit_cost=Decimal("999")),
        _row(2, Decimal("30"), unit_cost=Decimal("100")),
        _row(3, Decimal("4")),  # SOH without cost: counts units only
    ]
    out = summarise_soh_rows(rows, as_of=AS_OF, derived_mac=Decimal("120"))
    assert out["status"] == "available"
    assert out["period_start_date"] == "2026-09-14"
    assert out["row_count"] == 3
    assert out["soh_units"] == 44.0
    assert out["soh_unit_cost"] == 125.0  # (10*200 + 30*100) / 40
    assert out["cost_field"] == "mixed"
    assert out["derived_mac"] == 120.0
    assert out["delta"] == -5.0
    assert out["flags"] == []


def test_soh_without_cost_is_flagged_not_invented():
    out = summarise_soh_rows([_row(1, Decimal("7"))], as_of=AS_OF, derived_mac=Decimal("50"))
    assert out["status"] == "available"
    assert out["soh_units"] == 7.0
    assert out["soh_unit_cost"] is None
    assert out["flags"] == ["no_soh_cost"]
    assert "delta" not in out


def test_zero_soh_with_cost_has_no_weighted_cost():
    out = summarise_soh_rows(
        [_row(1, Decimal("0"), unit_cost=Decimal("80"))], as_of=AS_OF, derived_mac=Decimal("50")
    )
    assert out["status"] == "available"
    assert out["soh_units"] == 0.0
    assert out["soh_unit_cost"] is None
    assert out["cost_field"] == "unit_cost"
    assert out["flags"] == ["zero_soh"]
    assert "delta" not in out


def test_honest_unavailable_when_no_cst_soh_row():
    session = _session([])
    out = customer_soh_check(
        session, customer_id=1, product_id=2, as_of=AS_OF, derived_mac=Decimal("50")
    )
    assert out["status"] == "unavailable"
    assert out["flags"] == ["no_customer_soh"]
    assert "customer SOH unavailable" in out["reason"]
    assert "fact_customer_sellthrough" in out["reason"]
    assert "soh_units" not in out  # never reported as zero stock
    assert "fact_inventory_customer" not in repr(out)
