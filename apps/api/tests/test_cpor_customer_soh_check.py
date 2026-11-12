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
    resolve_stored_mac_vat,
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


def test_incl_vat_unit_cost_is_divided_by_1_15_before_compare():
    # 115 incl-VAT is 100 ex-VAT. Compared with a 100 ex-VAT MAC the gap is zero.
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("115"), vat="inc_vat")],
        as_of=AS_OF,
        derived_mac=Decimal("100"),
        tolerance_pct=Decimal("0.10"),
    )
    assert out["soh_unit_cost"] == 100.0
    assert out["soh_cost_vat"] == "ex_vat"
    assert out["vat_basis"] == "inc_vat"
    assert out["delta"] == 0.0
    assert "vat_basis_unknown" not in out["flags"]
    assert FLAG_SOH_TOLERANCE not in out["flags"]


def test_mixed_vat_bases_are_weighted_after_ex_vat_conversion():
    rows = [
        _row(1, Decimal("10"), unit_mac=Decimal("230"), unit_cost=Decimal("1"), vat="inc_vat"),
        _row(2, Decimal("10"), unit_cost=Decimal("80"), vat="ex_vat"),
    ]
    out = summarise_soh_rows(rows, as_of=AS_OF, derived_mac=Decimal("140"), tolerance_pct=Decimal("0.10"))
    # unit_mac wins on the incl row: 230 / 1.15 = 200. Then (10*200 + 10*80) / 20 = 140.
    assert out["soh_unit_cost"] == 140.0
    assert out["soh_cost_vat"] == "ex_vat"
    assert out["cost_field"] == "mixed"
    assert out["delta"] == 0.0
    assert "vat_basis_unknown" not in out["flags"]


def test_unknown_vat_basis_is_flagged_and_excluded_from_the_ex_vat_cost():
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("115"), vat=None)],
        as_of=AS_OF,
        derived_mac=Decimal("100"),
        tolerance_pct=Decimal("0.10"),
    )
    assert "vat_basis_unknown" in out["flags"]
    assert out["soh_unit_cost"] is None
    assert out["soh_cost_vat"] is None
    assert "delta" not in out
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert "no_soh_cost" not in out["flags"]


def test_blank_and_unrecognised_vat_basis_are_unknown():
    for vat in ("", "  ", "gross"):
        out = summarise_soh_rows(
            [_row(1, Decimal("4"), unit_mac=Decimal("50"), vat=vat)],
            as_of=AS_OF,
            derived_mac=Decimal("50"),
            tolerance_pct=Decimal("0.10"),
        )
        assert "vat_basis_unknown" in out["flags"], vat
        assert out["soh_unit_cost"] is None
        assert "delta" not in out


def test_unknown_basis_cost_is_left_out_of_a_known_ex_vat_average():
    rows = [
        _row(1, Decimal("10"), unit_cost=Decimal("115"), vat="inc_vat"),
        _row(2, Decimal("10"), unit_cost=Decimal("999"), vat=None),
    ]
    out = summarise_soh_rows(rows, as_of=AS_OF, derived_mac=Decimal("100"), tolerance_pct=Decimal("0.10"))
    assert out["soh_units"] == 20.0
    assert out["soh_unit_cost"] == 100.0
    assert out["soh_cost_vat"] == "ex_vat"
    assert "vat_basis_unknown" in out["flags"]
    assert out["delta"] == 0.0
    assert FLAG_SOH_TOLERANCE not in out["flags"]


def test_units_without_a_cost_do_not_raise_an_unknown_vat_flag():
    out = summarise_soh_rows([_row(1, Decimal("7"), vat=None)], as_of=AS_OF, derived_mac=Decimal("50"))
    assert out["flags"] == ["no_soh_cost"]
    assert out["soh_unit_cost"] is None


def test_stored_incl_vat_mac_is_divided_before_the_gap():
    # Review case: stored CST cost 115 incl-VAT against an ex-VAT SOH cost of 100.
    # 115 / 1.15 = 100, so the gap is zero and soh_tolerance must not fire.
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("100"), vat="ex_vat")],
        as_of=AS_OF,
        derived_mac=Decimal("115"),
        derived_mac_vat="inc_vat",
        tolerance_pct=Decimal("0.10"),
    )
    assert out["soh_unit_cost"] == 100.0
    assert out["derived_mac"] == 100.0
    assert out["derived_mac_input"] == 115.0
    assert out["derived_mac_input_vat"] == "inc_vat"
    assert out["delta"] == 0.0
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert "vat_basis_unknown" not in out["flags"]


def test_unknown_stored_mac_basis_withholds_the_comparison():
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("100"))],
        as_of=AS_OF,
        derived_mac=Decimal("115"),
        derived_mac_vat=None,
        tolerance_pct=Decimal("0.10"),
    )
    assert out["derived_mac"] == 115.0
    assert "derived_mac_input" not in out
    assert "delta" not in out
    assert "gap_pct" not in out
    assert "vat_basis_unknown" in out["flags"]
    assert FLAG_SOH_TOLERANCE not in out["flags"]


def test_explicit_ex_vat_mac_is_not_divided():
    out = summarise_soh_rows(
        [_row(1, Decimal("10"), unit_cost=Decimal("100"))],
        as_of=AS_OF,
        derived_mac=Decimal("115"),
        derived_mac_vat="ex_vat",
        tolerance_pct=Decimal("0.10"),
    )
    assert out["derived_mac"] == 115.0
    assert "derived_mac_input" not in out
    assert FLAG_SOH_TOLERANCE in out["flags"]


def test_manual_cost_is_compared_as_given():
    apply, basis = resolve_stored_mac_vat(
        MagicMock(),
        cost_source="manual",
        cost_evidence={},
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is False and basis is None


def test_sellout_cost_is_already_ex_vat():
    session = MagicMock()
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="sellout_evidence",
        cost_evidence={},
        cost_basis=Decimal("100"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "ex_vat"
    session.get.assert_not_called()
    session.execute.assert_not_called()


def test_cst_reported_line_uses_the_source_row_vat_basis():
    row = MagicMock()
    row.unit_cost = Decimal("115")
    row.vat_basis = "inc_vat"
    session = MagicMock()
    session.get = MagicMock(return_value=row)
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="cst_reported",
        cost_evidence={"fact_id": 9, "field_used": "unit_cost"},
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "inc_vat"
    session.get.assert_called_once()
    session.execute.assert_not_called()


def test_cst_line_without_a_matching_current_cost_withholds():
    session = MagicMock()
    res = MagicMock()
    res.first = MagicMock(return_value=(Decimal("80"), None, "inc_vat"))
    session.execute = MagicMock(return_value=res)
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="cst_reported",
        cost_evidence={},
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis is None


def test_cst_line_matches_the_current_incl_vat_cost():
    session = MagicMock()
    res = MagicMock()
    res.first = MagicMock(return_value=(None, Decimal("115"), "inc_vat"))
    session.execute = MagicMock(return_value=res)
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="cst_reported",
        cost_evidence={},
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "inc_vat"


def _fact(unit_mac=None, unit_cost=None, vat_basis=None):
    row = MagicMock()
    row.unit_mac = unit_mac
    row.unit_cost = unit_cost
    row.vat_basis = vat_basis
    return row


def _soh_100_ex_vat():
    return [_row(1, Decimal("10"), unit_cost=Decimal("100"), vat="ex_vat")]


def _gap_after_resolve(apply, basis, stored):
    """Run the resolved basis through the real comparison against SOH 100 ex-VAT."""
    kwargs = {"derived_mac_vat": basis} if apply else {}
    return summarise_soh_rows(
        _soh_100_ex_vat(),
        as_of=AS_OF,
        derived_mac=Decimal(stored),
        tolerance_pct=Decimal("0.10"),
        **kwargs,
    )


def _intake_fallback_evidence(snapshot_source, snapshot_evidence):
    # Shape written by suggest_intake_weighted_mac when it collapses to the CST snapshot.
    return {
        "composer": "intake_weighted_mac",
        "blend": {"collapsed_to_snapshot": True},
        "snapshot_fallback": {
            "cost_source": snapshot_source,
            "cost_basis": 115.0,
            "evidence": snapshot_evidence,
        },
    }


def test_r2f1_intake_weighted_cst_fallback_uses_the_cst_vat_basis():
    # Stored 115 incl-VAT (fallback to CST); SOH 100 ex-VAT. 115 / 1.15 = 100, delta 0.
    session = MagicMock()
    session.get = MagicMock(return_value=_fact(unit_cost=Decimal("115"), vat_basis="inc_vat"))
    evidence = _intake_fallback_evidence(
        "cst_reported", {"fact_id": 9, "field_used": "unit_cost", "unit_cost": 115.0}
    )
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="intake_weighted",
        cost_evidence=evidence,
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "inc_vat"
    out = _gap_after_resolve(apply, basis, "115")
    assert out["delta"] == 0.0
    assert FLAG_SOH_TOLERANCE not in out["flags"]


def test_r2f1_intake_weighted_sellout_fallback_is_ex_vat():
    evidence = _intake_fallback_evidence("sellout_evidence", {"tier": "sellout_evidence"})
    apply, basis = resolve_stored_mac_vat(
        MagicMock(),
        cost_source="intake_weighted",
        cost_evidence=evidence,
        cost_basis=Decimal("100"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "ex_vat"


def test_r2f1_intake_weighted_true_blend_withholds_the_gap():
    # A real blend mixes CST MAC with inbound unit_price (no VAT basis): provenance unknown.
    evidence = {
        "composer": "intake_weighted_mac",
        "blend": {"collapsed_to_snapshot": False},
        "cst_tier": {"fact_id": 9, "field_used": "unit_cost", "unit_cost": 115.0},
    }
    session = MagicMock()
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="intake_weighted",
        cost_evidence=evidence,
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis is None
    out = _gap_after_resolve(apply, basis, "115")
    assert "delta" not in out
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert "vat_basis_unknown" in out["flags"]


def test_r2f1_intake_weighted_without_evidence_withholds_the_gap():
    apply, basis = resolve_stored_mac_vat(
        MagicMock(),
        cost_source="intake_weighted",
        cost_evidence=None,
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis is None


def test_r2f2_reloaded_fact_with_a_new_basis_does_not_rebase_the_old_cost():
    # Stored 100 (was ex-VAT). The fact was reloaded in place: now 115 incl-VAT, same id.
    # Wrong: 100 / 1.15 = 86.96, gap 13.04 / 86.96 = 15% > 10% -> false flag. Must withhold.
    session = MagicMock()
    session.get = MagicMock(return_value=_fact(unit_cost=Decimal("115"), vat_basis="inc_vat"))
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="cst_reported",
        cost_evidence={"fact_id": 9, "field_used": "unit_cost", "unit_cost": 100.0},
        cost_basis=Decimal("100"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis is None
    out = _gap_after_resolve(apply, basis, "100")
    assert FLAG_SOH_TOLERANCE not in out["flags"]
    assert "vat_basis_unknown" in out["flags"]


def test_r2f2_fact_basis_is_used_when_the_referenced_field_still_matches():
    # The evidence names unit_mac as the field used; unit_cost differs and must not matter.
    session = MagicMock()
    session.get = MagicMock(
        return_value=_fact(unit_mac=Decimal("115"), unit_cost=Decimal("90"), vat_basis="inc_vat")
    )
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="cst_reported",
        cost_evidence={"fact_id": 9, "field_used": "unit_mac", "unit_mac": 115.0},
        cost_basis=Decimal("115"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "inc_vat"


def test_r2f2_stored_evidence_basis_wins_over_the_current_fact():
    # The basis was recorded with the cost; a later in-place reload to incl-VAT must not change it.
    session = MagicMock()
    session.get = MagicMock(return_value=_fact(unit_cost=Decimal("100"), vat_basis="inc_vat"))
    apply, basis = resolve_stored_mac_vat(
        session,
        cost_source="cst_reported",
        cost_evidence={
            "fact_id": 9,
            "field_used": "unit_cost",
            "unit_cost": 100.0,
            "vat_basis": "ex_vat",
        },
        cost_basis=Decimal("100"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis == "ex_vat"
    session.get.assert_not_called()


def test_r2f2_stored_evidence_basis_is_dropped_when_the_cost_was_edited():
    apply, basis = resolve_stored_mac_vat(
        MagicMock(),
        cost_source="cst_reported",
        cost_evidence={
            "fact_id": 9,
            "field_used": "unit_cost",
            "unit_cost": 100.0,
            "vat_basis": "ex_vat",
        },
        cost_basis=Decimal("130"),
        customer_id=1,
        product_id=2,
        as_of=AS_OF,
    )
    assert apply is True and basis is None


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

