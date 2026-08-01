"""Unit tests for B2 net-requirement pure math."""

from __future__ import annotations

from app.services.lineup.net_requirement import (
    NetRequirementInputs,
    compute_net_requirement,
)


def test_net_requirement_basic():
    r = compute_net_requirement(
        NetRequirementInputs(
            forecast_demand=100,
            channel_stock=20,
            in_transit=10,
            target_cover_units=40,
            bias_factor=0.0,
        )
    )
    # 100 - 20 - 10 + 40 = 110
    assert r.net_requirement == 110.0
    assert r.bias_adjusted_forecast == 100.0


def test_net_requirement_floors_at_zero():
    r = compute_net_requirement(
        NetRequirementInputs(
            forecast_demand=10,
            channel_stock=50,
            in_transit=20,
            target_cover_units=5,
        )
    )
    assert r.net_requirement == 0.0


def test_net_requirement_bias_inflates_forecast():
    r = compute_net_requirement(
        NetRequirementInputs(
            forecast_demand=100,
            channel_stock=0,
            in_transit=0,
            target_cover_units=0,
            bias_factor=0.10,
        )
    )
    assert r.bias_adjusted_forecast == 110.0
    assert r.net_requirement == 110.0
