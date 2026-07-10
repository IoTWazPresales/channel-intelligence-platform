"""Unit tests for shipping distributor display-name-first resolution (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.shipping_distributor_display import (
    is_tmp_distributor_code,
    name_looks_like_tmp_code,
    resolve_distributor_display,
    resolve_distributor_display_from_row,
)


def test_promoted_distributor_uses_name() -> None:
    label, provisional = resolve_distributor_display(
        distributor_name="Mustek Limited",
        distributor_code="DIST-MUSTEK",
    )
    assert label == "Mustek Limited"
    assert provisional is False


def test_tmp_with_human_name_prefers_name() -> None:
    label, provisional = resolve_distributor_display(
        distributor_name="Acme Distributors",
        distributor_code="TMP-DIST-20260608-ABCD",
    )
    assert label == "Acme Distributors"
    assert provisional is True


def test_tmp_name_equals_code_falls_through_to_bill_to() -> None:
    code = "TMP-DIST-20260608-ABCD"
    label, provisional = resolve_distributor_display(
        distributor_name=code,
        distributor_code=code,
        bill_to_raw="MUSTEK-ZA-BB",
    )
    assert label == "MUSTEK-ZA-BB"
    assert provisional is True


def test_tmp_code_only_uses_suggested_token_name() -> None:
    label, provisional = resolve_distributor_display(
        distributor_name=None,
        distributor_code="TMP-DIST-20260608-ABCD",
        distributor_resolution_token="MUSTEK-ZA-BB",
    )
    # suggested_name_for_distributor_token strips -ZA-BB → Mustek
    assert "Mustek" in label or label == "MUSTEK-ZA-BB"
    assert provisional is True
    assert not label.upper().startswith("TMP-DIST")


def test_tmp_code_only_no_evidence_returns_code() -> None:
    code = "TMP-DIST-20260608-ABCD"
    label, provisional = resolve_distributor_display(
        distributor_name=code,
        distributor_code=code,
    )
    assert label == code
    assert provisional is True


def test_non_tmp_code_when_name_missing() -> None:
    label, provisional = resolve_distributor_display(
        distributor_name=None,
        distributor_code="DIST-RECTRON",
    )
    assert label == "DIST-RECTRON"
    assert provisional is False


def test_is_tmp_helpers() -> None:
    assert is_tmp_distributor_code("TMP-DIST-1") is True
    assert is_tmp_distributor_code("tmp-dist-1") is True
    assert is_tmp_distributor_code("DIST-1") is False
    assert name_looks_like_tmp_code("TMP-DIST-1", "TMP-DIST-1") is True
    assert name_looks_like_tmp_code("Acme", "TMP-DIST-1") is False


def test_from_row_adapter() -> None:
    row = SimpleNamespace(
        bill_to_raw="Bill To Co",
        ship_to_raw=None,
        distributor_resolution_token=None,
    )
    code = "TMP-DIST-X"
    label, provisional = resolve_distributor_display_from_row(row, code, code)
    assert label == "Bill To Co"
    assert provisional is True
