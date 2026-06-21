"""Unit tests for provisional entity canonical identity (no database)."""

from __future__ import annotations

from app.services.imports.provisional_entity_identity import (
    canonical_provisional_entity_name_key,
    is_non_entity_customer_provisional_token,
)


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
