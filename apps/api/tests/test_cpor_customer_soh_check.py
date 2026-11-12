"""N-0049 / BACKLOG-135 / D-0038 — customer SOH check reads CST (mocked session; no DB writes)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.cpor.customer_soh_check import (
    DEFAULT_SOH_TOLERANCE_PCT,
    FLAG_SOH_TOLERANCE,
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
    # Multi-site week: unit_mac wins over unit_cost per row. Gap 5/120 < 10% — no tolerance flag.
    rows = [
        _row(1, Decimal("10"), unit_mac=Decimal("200"), unit_cost=Decimal("999")),
        _row(2, Decimal("30"), unit_cost=Decimal("100")),
        _row(3, Decimal("4")),  # SOH without cost: counts units only
    ]
    out = summarise_soh_rows(rows, as_of=AS_OF, derived_mac=Decimal("120"), tolerance_pct=Decimal("0.10"))
    assert out["status"] == "available"
    assert out["period_start_date"] == "2026-09-14"
    assert out["row_count"] == 3
    assert out["soh_units"] == 44.0
    assert out["soh_unit_cost"] == 125.0  # (10*200 + 30*100) / 40
    assert out["cost_field"] == "mixed"
    assert out["derived_mac"] == 120.0
    assert out["delta"] == -5.0
    assert out["tolerance_pct"] == 0.10
    assert abs(out["gap_pct"] - (5.0 / 120.0)) < 1e-9
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert out["flags"] == []


def test_soh_without_cost_is_flagged_not_invented():
    # Evetech-style: units only — no cost, no cost-tolerance flag.
    out = summarise_soh_rows([_row(1, Decimal("7"))], as_of=AS_OF, derived_mac=Decimal("50"))
    assert out["status"] == "available"
    assert out["soh_units"] == 7.0
    assert out["soh_unit_cost"] is None
    assert out["flags"] == ["no_soh_cost"]
    assert "delta" not in out
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert "gap_pct" not in out


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


def test_tolerance_flag_when_gap_exceeds_default_10_pct():
    # soh_cost 100, derived 80 -> gap 20/80 = 25% > 10%
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("100"))],
        as_of=AS_OF,
        derived_mac=Decimal("80"),
        tolerance_pct=DEFAULT_SOH_TOLERANCE_PCT,
    )
    assert out["delta"] == -20.0
    assert out["tolerance_pct"] == 0.10
    assert abs(out["gap_pct"] - 0.25) < 1e-9
    assert FLAG_SOH_TOLERANCE in out["flags"]


def test_tolerance_flag_respects_custom_threshold():
    # Same 25% gap is inside a 30% tenant setting.
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("100"))],
        as_of=AS_OF,
        derived_mac=Decimal("80"),
        tolerance_pct=Decimal("0.30"),
    )
    assert abs(out["gap_pct"] - 0.25) < 1e-9
    assert FLAG_SOH_TOLERANCE not in out["flags"]


def test_tolerance_exact_boundary_is_not_flagged():
    # gap == tolerance is inside (flag only when strictly greater).
    out = summarise_soh_rows(
        [_row(1, Decimal("1"), unit_cost=Decimal("110"))],
        as_of=AS_OF,
        derived_mac=Decimal("100"),
        tolerance_pct=Decimal("0.10"),
    )
    assert out["delta"] == -10.0
    assert abs(out["gap_pct"] - 0.10) < 1e-9
    assert FLAG_SOH_TOLERANCE not in out["flags"]


def test_zero_derived_mac_with_nonzero_soh_cost_flags():
    out = summarise_soh_rows(
        [_row(1, Decimal("2"), unit_cost=Decimal("50"))],
        as_of=AS_OF,
        derived_mac=Decimal("0"),
        tolerance_pct=Decimal("0.10"),
    )
    assert out["delta"] == -50.0
    assert out["gap_pct"] is None
    assert FLAG_SOH_TOLERANCE in out["flags"]


def test_tolerance_uses_tenant_default_when_pct_omitted(monkeypatch):
    from app.services import commercial_tenant_profile as ctp

    monkeypatch.setattr(ctp, "load_tenant_profile_overrides", lambda tenant_id="default": {})
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("100"))],
        as_of=AS_OF,
        derived_mac=Decimal("80"),
        tenant_id="default",
    )
    assert out["tolerance_pct"] == 0.10
    assert FLAG_SOH_TOLERANCE in out["flags"]



# --- BACKLOG-135 VAT rule (Warren 2026-11-10): compare ex-VAT; incl-VAT costs / 1.15; flag unknown basis.


def test_inc_vat_cost_is_divided_by_one_plus_vat_rate_before_compare():
    # 115 incl-VAT at 15% -> 100 ex-VAT; derived MAC 100 -> no gap.
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("115"), vat="inc_vat")],
        as_of=AS_OF,
        derived_mac=Decimal("100"),
        tolerance_pct=Decimal("0.10"),
        vat_rate_pct=Decimal("0.15"),
    )
    assert out["soh_unit_cost"] == 100.0
    assert out["soh_cost_vat_basis"] == "ex_vat"
    assert out["vat_converted_rows"] == 1
    assert out["vat_rate_pct"] == 0.15
    assert out["vat_basis"] == "inc_vat"  # source basis still reported
    assert out["delta"] == 0.0
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert "vat_basis_unknown" not in out["flags"]


def test_mixed_bases_convert_per_row_before_weighting():
    rows = [
        _row(1, Decimal("10"), unit_cost=Decimal("230"), vat="inc_vat"),  # 200 ex
        _row(2, Decimal("30"), unit_cost=Decimal("100"), vat="ex_vat"),
    ]
    out = summarise_soh_rows(rows, as_of=AS_OF, vat_rate_pct=Decimal("0.15"))
    assert out["soh_unit_cost"] == 125.0  # (10*200 + 30*100) / 40
    assert out["vat_converted_rows"] == 1
    assert out["vat_basis"] == ["ex_vat", "inc_vat"]
    assert out["flags"] == []


def test_ex_vat_rows_need_no_rate_and_are_unchanged():
    out = summarise_soh_rows(
        [_row(1, Decimal("4"), unit_mac=Decimal("80"), vat="ex_vat")], as_of=AS_OF
    )
    assert out["soh_unit_cost"] == 80.0
    assert out["vat_converted_rows"] == 0
    assert "vat_rate_pct" not in out
    assert out["flags"] == []


def test_unknown_vat_basis_on_a_costed_row_is_flagged_not_converted():
    for basis in (None, "", "gross"):
        out = summarise_soh_rows(
            [_row(1, Decimal("2"), unit_cost=Decimal("50"), vat=basis)],
            as_of=AS_OF,
            vat_rate_pct=Decimal("0.15"),
        )
        assert out["soh_unit_cost"] == 50.0, basis
        assert "vat_basis_unknown" in out["flags"], basis
        assert out["vat_converted_rows"] == 0


def test_unknown_basis_on_units_only_row_is_not_flagged():
    # No cost figure on the row, so there is no VAT basis to know.
    out = summarise_soh_rows([_row(1, Decimal("7"), vat=None)], as_of=AS_OF)
    assert out["flags"] == ["no_soh_cost"]


def test_inc_vat_uses_tenant_vat_rate_when_omitted(monkeypatch):
    from app.services import commercial_tenant_profile as ctp

    monkeypatch.setattr(ctp, "load_tenant_profile_overrides", lambda tenant_id="default": {})
    out = summarise_soh_rows(
        [_row(1, Decimal("1"), unit_cost=Decimal("115"), vat="INC_VAT")],
        as_of=AS_OF,
        tenant_id="default",
    )
    assert out["vat_rate_pct"] == 0.15
    assert out["soh_unit_cost"] == 100.0
