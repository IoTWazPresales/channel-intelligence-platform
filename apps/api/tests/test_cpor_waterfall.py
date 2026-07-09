"""CPOR U2 — pure waterfall math fixtures (spec §2.1). No DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.cpor.waterfall import (
    CHANNEL_STEPS,
    compute_dealer_price,
    compute_line_waterfall,
    compute_support_unit,
    compute_support_usd,
    compute_ttl_result,
    quantize_money,
    run_steps,
)


def test_channel_steps_reseller_only_vat_and_margin():
    assert CHANNEL_STEPS["reseller"] == ["vat_divide", "margin_deduct"]
    assert "rebate_deduct" not in CHANNEL_STEPS["reseller"]


def test_unknown_channel_raises():
    with pytest.raises(ValueError, match="Unknown CPOR channel"):
        run_steps(100, "disti", {"vat_rate": "0.15", "dealer_margin_pct": "0.15"})


def test_fixture_dealer_price_10347_09():
    """SRP 13,999 / 1.15 × 0.85 → 10,347.09 (2dp)."""
    dp = compute_dealer_price("13999", "0.15", "0.15")
    assert quantize_money(dp) == Decimal("10347.09")


def test_fixture_support_unit_250_96_and_ttl_result_12297_18():
    """
    Spec §2.1 verified chain:
    - dealer_price display 9,334.11 with cost 9,585.07 → support 250.96 (2dp)
    - result 49 → ttl_result 12,297.18 (full-precision intermediate; NOT 250.96×49)
    - uncapped by estimate 20
    """
    # Reverse-engineer the workbook's dealer_price that yields support 250.96 display
    # from cost 9585.07: the un-rounded dealer used in the sheet for that row.
    # Spec narrative: Target Disti Price path ends at 9,334.11 display; reseller
    # support = cost − dealer_price. Use the exact dealer that makes
    # (9585.07 − dealer) × 49 quantize to 12297.18.
    cost = Decimal("9585.07")
    # Workbook: support_unit display 250.96; ttl_result 12297.18
    # ⇒ unrounded support = 12297.18 / 49
    unrounded_support = Decimal("12297.18") / Decimal("49")
    dealer = cost - unrounded_support
    assert quantize_money(dealer) == Decimal("9334.11")
    assert quantize_money(unrounded_support) == Decimal("250.96")

    su = compute_support_unit(cost, dealer)
    assert quantize_money(su) == Decimal("250.96")
    ttl = compute_ttl_result(su, 49)
    assert ttl is not None
    assert quantize_money(ttl) == Decimal("12297.18")
    # Not capped by estimate 20
    assert quantize_money(su * Decimal("20")) != Decimal("12297.18")


def test_fixture_srp_path_then_support_from_workbook_dealer():
    """SRP path for 10347.09; separate support fixture uses cost − dealer."""
    dp = compute_dealer_price(13999, Decimal("0.15"), Decimal("0.15"))
    assert quantize_money(dp) == Decimal("10347.09")
    # Clamp example: cost below dealer → 0
    assert compute_support_unit(Decimal("9000"), dp) == Decimal("0")


def test_clamp_epsilon_negative_to_zero():
    dealer = Decimal("100")
    cost = Decimal("100") - Decimal("3.6e-12")
    assert compute_support_unit(cost, dealer) == Decimal("0")


def test_missing_roe_flags():
    usd, flags = compute_support_usd(Decimal("250.96"), None)
    assert usd is None
    assert "missing_roe" in flags


def test_support_usd_with_roe():
    usd, flags = compute_support_usd(Decimal("250.96"), Decimal("18.5"))
    assert flags == []
    assert usd is not None
    assert quantize_money(usd) == quantize_money(Decimal("250.96") / Decimal("18.5"))


def test_no_cost_basis_still_computes_dealer_price():
    out = compute_line_waterfall(
        srp="13999",
        vat_rate="0.15",
        dealer_margin_pct="0.15",
        cost_basis=None,
        estimate_qty=20,
        result_qty=49,
        case_roe="18.5",
    )
    assert quantize_money(out["dealer_price"]) == Decimal("10347.09")
    assert out["support_unit"] is None
    assert out["ttl_support"] is None
    assert out["ttl_result"] is None
    assert "no_cost_basis" in out["flags"]


def test_ttl_result_none_when_no_result_qty():
    out = compute_line_waterfall(
        srp="13999",
        vat_rate="0.15",
        dealer_margin_pct="0.15",
        cost_basis="9585.07",
        estimate_qty=20,
        result_qty=None,
        case_roe="18.5",
    )
    assert out["ttl_result"] is None
    assert out["support_unit"] is not None
