"""Pure helpers for provisional steward display names (no database)."""

from __future__ import annotations

from types import SimpleNamespace


def test_default_display_name_customer_prefers_dealer_group_account_raw() -> None:
    from app.services.imports.dsi_steward_candidate_ops import default_display_name_provisional_customer

    c = SimpleNamespace(
        context={"dealer_group_account_raw": "  DEALER CO  "},
        dealer_group_token=None,
        normalized_key="nk",
        sample_raw_values=[],
    )
    assert default_display_name_provisional_customer(c) == "DEALER CO"


def test_default_display_name_customer_falls_back_to_dealer_group_token() -> None:
    from app.services.imports.dsi_steward_candidate_ops import default_display_name_provisional_customer

    c = SimpleNamespace(
        context={},
        dealer_group_token="TOKEN_X",
        normalized_key="nk",
        sample_raw_values=[],
    )
    assert default_display_name_provisional_customer(c) == "TOKEN_X"


def test_default_display_name_distributor_uses_sample() -> None:
    from app.services.imports.dsi_steward_candidate_ops import default_display_name_provisional_distributor

    c = SimpleNamespace(sample_raw_values=[" Dist Alpha "], normalized_key="nk")
    assert default_display_name_provisional_distributor(c) == "Dist Alpha"


def test_default_display_name_distributor_unknown_when_empty() -> None:
    from app.services.imports.dsi_steward_candidate_ops import default_display_name_provisional_distributor

    c = SimpleNamespace(sample_raw_values=[], normalized_key="__blank__")
    assert default_display_name_provisional_distributor(c) == "Unknown distributor"
