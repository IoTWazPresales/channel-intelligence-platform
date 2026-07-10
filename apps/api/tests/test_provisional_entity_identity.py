"""Unit tests for provisional entity canonical identity (no database)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.imports.provisional_entity_identity import (
    canonical_provisional_entity_name_key,
    is_non_entity_customer_provisional_token,
    pick_provisional_customer_for_reuse,
)


@dataclass
class _CustRow:
    id: int
    name: str
    code: str = "TMP-CUST-TEST"
    customer_status: str = "unverified"


def test_canonical_name_key_case_and_punctuation() -> None:
    assert canonical_provisional_entity_name_key("Mustek") == canonical_provisional_entity_name_key("MUSTEK")
    assert canonical_provisional_entity_name_key("Pinnacle (ZA)") == canonical_provisional_entity_name_key(
        "pinnacle za"
    )
    assert canonical_provisional_entity_name_key("  Rectron  ") == "rectron"


def test_non_entity_customer_employee_terms() -> None:
    assert is_non_entity_customer_provisional_token(
        raw_token="Employee Terms and Conditions",
        display_name=None,
    )
    assert is_non_entity_customer_provisional_token(
        raw_token=None,
        display_name="ACME Staff Purchase Program",
    )
    assert not is_non_entity_customer_provisional_token(
        raw_token="Compuspeed",
        display_name="Compuspeed",
    )


def test_pick_provisional_customer_reuses_similarity_suffix_variant() -> None:
    existing = _CustRow(id=17, name="BT GAMES (PTY) LTD")
    rows = [existing, _CustRow(id=99, name="Totally Different Retailer Ltd")]
    pick = pick_provisional_customer_for_reuse(rows, "BT Games")
    assert pick is not None
    assert pick.id == 17


def test_pick_provisional_customer_no_match_for_new_name() -> None:
    rows = [_CustRow(id=17, name="BT GAMES (PTY) LTD")]
    assert pick_provisional_customer_for_reuse(rows, "Brand New Shop CC") is None


def test_pick_provisional_customer_similarity_ambiguous_returns_none(caplog: pytest.LogCaptureFixture) -> None:
    rows = [
        _CustRow(id=1, name="Foo Bar Pty Ltd"),
        _CustRow(id=2, name="Foo Bar (Pty) Ltd"),
    ]
    assert pick_provisional_customer_for_reuse(rows, "Foo Bar") is None
    assert "provisional_customer_similarity_ambiguous" in caplog.text


def test_pick_provisional_customer_canonical_still_wins_before_similarity() -> None:
    rows = [_CustRow(id=5, name="Rectron")]
    pick = pick_provisional_customer_for_reuse(rows, "  RECTRON  ")
    assert pick is not None
    assert pick.id == 5
    assert canonical_provisional_entity_name_key("Rectron") == canonical_provisional_entity_name_key("  RECTRON  ")
