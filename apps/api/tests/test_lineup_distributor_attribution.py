"""Unit tests for D-040 confirmer evaluate rules (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.commercial_planner.lineup_distributor_attribution import (
    STATUS_CONFLICT,
    STATUS_SHIPMENT_CONFIRMED,
    STATUS_TOKEN_PROPOSED,
    _ShipHit,
    _evaluate_token_group,
    _sole_dap_price_distributor,
)


def _ln(**kw):
    defaults = dict(
        id=1,
        case_id=10,
        product_id=100,
        quantity_units=36.0,
        distributor_id=None,
        distributor_attribution_status=None,
        dap_evidence_local=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_sole_exact_offers_accept_when_null_dist():
    lines = [_ln(id=1, distributor_id=None)]
    ships = [_ShipHit(100, 45, 36.0, 9)]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["sole_exact_distributor_id"] == 45
    assert out["ship_corroboration_offer"]["distributor_id"] == 45
    assert out["per_line"][0]["action"] == "offer_accept"


def test_sole_exact_confirms_matching_proposed():
    lines = [_ln(id=1, distributor_id=45, distributor_attribution_status=STATUS_TOKEN_PROPOSED)]
    ships = [_ShipHit(100, 45, 36.0, 9)]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["per_line"][0]["action"] == "confirm"
    assert out["per_line"][0]["new_status"] == STATUS_SHIPMENT_CONFIRMED


def test_multi_dist_leaves_proposed_when_present():
    lines = [_ln(id=1, distributor_id=12, distributor_attribution_status=STATUS_TOKEN_PROPOSED)]
    ships = [
        _ShipHit(100, 12, 99.0, 1),
        _ShipHit(100, 21, 99.0, 2),
    ]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["per_line"][0]["action"] == "leave_proposed"
    assert out["sole_exact_distributor_id"] is None


def test_absent_proposed_sets_conflict_keeps_semantics():
    lines = [_ln(id=1, distributor_id=14, distributor_attribution_status=STATUS_TOKEN_PROPOSED)]
    ships = [_ShipHit(100, 21, 36.0, 1), _ShipHit(100, 29, 36.0, 2)]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["per_line"][0]["action"] == "conflict"
    assert out["per_line"][0]["new_status"] == STATUS_CONFLICT
    assert out["per_line"][0]["distributor_id"] == 14  # never cleared in evaluate


def test_no_ships_noop():
    lines = [_ln(id=1, distributor_id=12, distributor_attribution_status=STATUS_TOKEN_PROPOSED)]
    out = _evaluate_token_group(
        token_lines=lines, ships=[], isolated_products={100}
    )
    assert out["per_line"][0]["action"] == "no_ships"


def test_sole_dap_helper_unique_within_tol():
    ships = [
        _ShipHit(100, 12, 36.0, 1, unit_price=100.0),
        _ShipHit(100, 21, 36.0, 2, unit_price=200.0),
    ]
    assert _sole_dap_price_distributor(dap=100.0, ships=ships) == 12


def test_sole_dap_helper_ambiguous_when_two_within_tol():
    ships = [
        _ShipHit(100, 12, 36.0, 1, unit_price=100.0),
        _ShipHit(100, 21, 36.0, 2, unit_price=101.0),
    ]
    assert _sole_dap_price_distributor(dap=100.0, ships=ships) is None


def test_phase2_dap_confirms_when_multi_exact_qty():
    lines = [
        _ln(
            id=1,
            distributor_id=12,
            distributor_attribution_status=STATUS_TOKEN_PROPOSED,
            dap_evidence_local=100.0,
        )
    ]
    ships = [
        _ShipHit(100, 12, 36.0, 1, unit_price=100.0),
        _ShipHit(100, 21, 36.0, 2, unit_price=200.0),
    ]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["sole_exact_distributor_id"] is None
    assert out["per_line"][0]["action"] == "confirm_price"
    assert out["per_line"][0]["confirm_via"] == "dap_unit_price"
    assert out["per_line"][0]["new_status"] == STATUS_SHIPMENT_CONFIRMED
    assert out["ship_corroboration_offer"]["reason"] == "sole_resolved_distributor_dap_unit_price"


def test_phase2_dap_conflict_when_proposed_differs():
    lines = [
        _ln(
            id=1,
            distributor_id=21,
            distributor_attribution_status=STATUS_TOKEN_PROPOSED,
            dap_evidence_local=100.0,
        )
    ]
    ships = [
        _ShipHit(100, 12, 36.0, 1, unit_price=100.0),
        _ShipHit(100, 21, 36.0, 2, unit_price=200.0),
    ]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["per_line"][0]["action"] == "conflict_price"
    assert out["per_line"][0]["new_status"] == STATUS_CONFLICT
    assert out["per_line"][0]["distributor_id"] == 21


def test_phase2_dap_offer_when_null_dist():
    lines = [_ln(id=1, distributor_id=None, dap_evidence_local=100.0)]
    ships = [
        _ShipHit(100, 12, 36.0, 1, unit_price=100.0),
        _ShipHit(100, 21, 36.0, 2, unit_price=200.0),
    ]
    out = _evaluate_token_group(
        token_lines=lines, ships=ships, isolated_products={100}
    )
    assert out["per_line"][0]["action"] == "offer_accept_price"
    assert out["ship_corroboration_offer"]["distributor_id"] == 12
