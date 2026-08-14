"""Unit 15A — intake-weighted MAC composer (mocked session; no cip writes)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.cpor.cost_suggestion import CostSuggestion, detect_cost_basis_drift
from app.services.cpor.intake_weighted_mac import suggest_intake_weighted_mac
from app.services.cpor.waterfall import quantize_money


def _cst(mac: str = "100") -> CostSuggestion:
    return CostSuggestion(
        cost_basis=Decimal(mac),
        cost_source="cst_reported",
        evidence={"as_of": "2026-05-01", "field_used": "unit_mac", "tier": "cst_reported"},
        flags=[],
    )


def _call(**overrides):
    session = MagicMock()
    kwargs = dict(
        customer_id=1,
        product_id=2,
        distributor_id=3,
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 30),
        as_of=date(2026, 6, 15),
    )
    kwargs.update(overrides)
    return suggest_intake_weighted_mac(session, **kwargs)


@patch("app.services.cpor.intake_weighted_mac._disti_cost_proxy_wavg", return_value=(Decimal("80"), date(2026, 1, 1), ["dsi_wac_not_ingested", "disti_cost_is_intake_proxy"]))
@patch("app.services.cpor.intake_weighted_mac._latest_sellout_unit_amount", return_value=(Decimal("500"), date(2026, 6, 1)))
@patch("app.services.cpor.intake_weighted_mac._forward_supply_qty", return_value=Decimal("12"))
@patch(
    "app.services.cpor.intake_weighted_mac._intake_wavg",
    return_value=(Decimal("5"), Decimal("200"), date(2026, 6, 15), ["intake_is_oem_sell_in_evidence"]),
)
@patch("app.services.cpor.intake_weighted_mac._tier1_cst", return_value=_cst("100"))
@patch(
    "app.services.cpor.intake_weighted_mac._on_hand_qty",
    return_value=(Decimal("10"), date(2026, 6, 1), []),
)
def test_blend_two_cost_buckets(*_patches):
    sug = _call()
    # (10×100 + 5×200) / 15 = 133.333…
    assert sug.cost_source == "intake_weighted"
    assert sug.cost_basis is not None
    assert quantize_money(sug.cost_basis) == Decimal("133.33")
    assert "intake_is_oem_sell_in_evidence" in sug.flags
    assert "cross_grain_valuation" in sug.flags
    ev = sug.evidence
    assert ev["bucket_a_on_hand"]["qty"] == 10.0
    assert ev["bucket_a_on_hand"]["unit_cost"] == 100.0
    assert ev["bucket_b_intake"]["qty"] == 5.0
    assert ev["bucket_b_intake"]["unit_cost"] == 200.0
    assert ev["bucket_a_on_hand"]["as_of"] == "2026-06-01"
    assert ev["bucket_b_intake"]["as_of"] == "2026-06-15"
    # Display legs present, not blended
    assert ev["sellout_value"]["unit_amount"] == 500.0
    assert ev["sellout_value"]["value"] == 5000.0
    assert "sellout_value_display_only" in ev["sellout_value"]["flags"]
    assert "planned_supply_no_native_cost" in ev["planned_supply"]["flags"]
    assert ev["planned_supply"]["qty"] == 12.0
    assert "dsi_wac_not_ingested" in ev["disti_cost"]["flags"]
    assert "disti_cost_is_intake_proxy" in ev["disti_cost"]["flags"]
    assert sug.cost_basis != Decimal("500")
    assert "unit_cost" not in str(ev["sellout_value"].get("field"))
    dumped = str(ev)
    assert "System Price" not in dumped
    assert "Total Average Cost" not in dumped
    assert ev["blend"]["collapsed_to_snapshot"] is False


@patch("app.services.cpor.intake_weighted_mac.suggest_cost_basis", return_value=_cst("100"))
@patch("app.services.cpor.intake_weighted_mac._disti_cost_proxy_wavg", return_value=(None, None, ["dsi_wac_not_ingested"]))
@patch("app.services.cpor.intake_weighted_mac._latest_sellout_unit_amount", return_value=(Decimal("500"), date(2026, 6, 1)))
@patch("app.services.cpor.intake_weighted_mac._forward_supply_qty", return_value=Decimal("0"))
@patch(
    "app.services.cpor.intake_weighted_mac._intake_wavg",
    return_value=(Decimal("0"), None, None, ["no_intake_evidence"]),
)
@patch("app.services.cpor.intake_weighted_mac._tier1_cst", return_value=_cst("100"))
@patch(
    "app.services.cpor.intake_weighted_mac._on_hand_qty",
    return_value=(Decimal("10"), date(2026, 6, 1), []),
)
def test_empty_intake_falls_back_to_snapshot_and_amount_is_display_only(*_patches):
    sug = _call()
    assert "no_intake_evidence" in sug.flags
    assert sug.cost_source == "cst_reported"
    assert sug.cost_basis == Decimal("100")
    assert sug.evidence["blend"]["collapsed_to_snapshot"] is True
    assert sug.evidence["sellout_value"]["unit_amount"] == 500.0
    assert "sellout_value_display_only" in sug.flags
    # Amount must not become MAC
    assert sug.cost_basis != Decimal("500")
    assert "sellout_value_display_only" in sug.evidence["not_in_blend"]


@patch("app.services.cpor.intake_weighted_mac._disti_cost_proxy_wavg", return_value=(None, None, ["dsi_wac_not_ingested"]))
@patch("app.services.cpor.intake_weighted_mac._latest_sellout_unit_amount", return_value=(None, None))
@patch("app.services.cpor.intake_weighted_mac._forward_supply_qty", return_value=Decimal("0"))
@patch(
    "app.services.cpor.intake_weighted_mac._intake_wavg",
    return_value=(Decimal("8"), Decimal("50"), date(2026, 6, 10), ["intake_is_oem_sell_in_evidence"]),
)
@patch("app.services.cpor.intake_weighted_mac._tier1_cst", return_value=_cst("100"))
@patch(
    "app.services.cpor.intake_weighted_mac._on_hand_qty",
    return_value=(Decimal("0"), None, ["no_soh_evidence"]),
)
def test_empty_soh_flags_and_intake_only_blend(*_patches):
    sug = _call()
    assert "no_soh_evidence" in sug.flags
    assert sug.cost_source == "intake_weighted"
    assert sug.cost_basis == Decimal("50")
    assert "cross_grain_valuation" not in sug.flags


def test_approve_drift_flags_without_rewriting_stored_cost():
    from app.api.v1.endpoints import cpor_cases

    session = MagicMock()
    line = SimpleNamespace(
        id=1,
        product_id=2,
        cost_basis=Decimal("100"),
        cost_evidence_json={},
    )
    session.scalars.return_value.all.return_value = [line]
    case = SimpleNamespace(id=9, customer_id=1, created_at=None)
    fresh = CostSuggestion(
        cost_basis=Decimal("120"),
        cost_source="cst_reported",
        evidence={"tier": "cst_reported"},
        flags=[],
    )
    with patch.object(cpor_cases, "suggest_cost_basis", return_value=fresh):
        with patch.object(cpor_cases, "_record_event"):
            drifts = cpor_cases._run_drift_check(session, case, actor="test")
    assert line.cost_basis == Decimal("100")
    assert drifts and drifts[0]["flag"] == "cost_basis_drift"
    assert "cost_basis_drift" in (line.cost_evidence_json.get("flags") or [])
    # Same detect helper, still FLAG-only
    assert detect_cost_basis_drift(Decimal("100"), fresh)["flag"] == "cost_basis_drift"
