"""U4: VAT and CPOR names come from the tenant profile. No built-in 15% and no built-in type list."""

from __future__ import annotations

import pytest

from app.services import commercial_tenant_profile as profile
from app.services.channel_intelligence.sell_through_overview import convert_reported_money
from app.services.cpor.promotion_type_vocab import (
    require_channel,
    require_promotion_type,
    stock_promote_type,
)


@pytest.fixture
def tenant_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    return tmp_path


def test_unset_vat_rate_is_none(tenant_dir):
    assert profile.configured_vat_rate_pct("acme") is None
    assert profile.vat_rate_pct("acme") is None
    snap = profile.profile_snapshot("acme")
    assert snap["vat_rate_pct"] is None
    assert snap["vat_rate_not_configured"] is True


def test_named_country_without_a_rate_uses_the_tenant_rate(tenant_dir):
    # Warren 27 Nov: VAT comes from the row, else the data's country, else the tenant rate.
    profile.save_tenant_profile_overrides(
        "acme",
        {"vat_rate_pct": "0.2", "vat_rate_by_country": {"ZA": "0.15"}},
    )
    assert profile.vat_rate_for_data("acme", "ZA") == pytest.approx(0.15)
    assert profile.vat_rate_for_data("acme", "DE") == pytest.approx(0.2)
    assert profile.vat_rate_for_data("acme", None) == pytest.approx(0.2)


def test_saved_vat_rate_is_returned(tenant_dir):
    profile.save_tenant_profile_overrides("acme", {"vat_rate_pct": "0.2"})
    assert profile.vat_rate_pct("acme") == pytest.approx(0.2)
    assert profile.profile_snapshot("acme")["vat_rate_not_configured"] is False


def test_promotion_types_empty_until_saved(tenant_dir):
    assert profile.cpor_promotion_types("acme") == ()
    assert profile.cpor_channels("acme") == ()
    assert stock_promote_type("acme") is None
    with pytest.raises(ValueError, match="promotion_type_not_configured"):
        require_promotion_type("acme", "Sell out PP")
    with pytest.raises(ValueError, match="channel_not_configured"):
        require_channel("acme", None)


def test_saved_promotion_vocab_round_trip(tenant_dir):
    saved = profile.save_tenant_profile_overrides(
        "acme",
        {
            "cpor_promotion_types": ["Sell out PP", "Sell-Through PP", "Stock PP (In-Direct)"],
            "cpor_channels": ["reseller"],
            "cpor_stock_promote_type": "Stock PP (In-Direct)",
        },
    )
    assert saved["cpor_promotion_types"] == [
        "Sell out PP",
        "Sell-Through PP",
        "Stock PP (In-Direct)",
    ]
    assert profile.cpor_channels("acme") == ("reseller",)
    assert stock_promote_type("acme") == "Stock PP (In-Direct)"
    with pytest.raises(ValueError, match="promotion_type_required"):
        require_promotion_type("acme", None)
    assert require_channel("acme", None) == "reseller"
    assert require_promotion_type("acme", "Sell-Through PP") == "Sell-Through PP"


def test_stock_promote_type_must_be_one_of_the_saved_types(tenant_dir):
    with pytest.raises(ValueError, match="must be one of"):
        profile.save_tenant_profile_overrides(
            "acme",
            {
                "cpor_promotion_types": ["Sell out PP"],
                "cpor_stock_promote_type": "Stock PP (In-Direct)",
            },
        )


def test_convert_reported_money_withholds_when_the_rate_is_unset():
    assert convert_reported_money(115, row_includes_vat=True, want_includes_vat=True, vat_rate=None) == 115
    assert (
        convert_reported_money(115, row_includes_vat=True, want_includes_vat=False, vat_rate=None)
        is None
    )
    assert convert_reported_money(100, row_includes_vat=False, want_includes_vat=True, vat_rate=0.15) == pytest.approx(
        115
    )
