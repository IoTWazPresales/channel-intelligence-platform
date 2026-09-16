"""Exact Case ID focus for payment-evidence ?code= — no database, no mint."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.cpor.payment_evidence.overlay_read import (
    evidence_rows_matching_exact_code,
    exact_case_code,
    serialize_payment_evidence_focus_row,
)


def test_exact_case_code_trims_only():
    assert exact_case_code("  C19A50693  ") == "C19A50693"
    assert exact_case_code("") is None
    assert exact_case_code("   ") is None
    assert exact_case_code(None) is None


def test_exact_match_rejects_prefix_and_casefold():
    rows = [
        SimpleNamespace(external_case_code="C19A50693"),
        SimpleNamespace(external_case_code="C19A50693X"),
        SimpleNamespace(external_case_code="c19a50693"),
    ]
    hit = evidence_rows_matching_exact_code(rows, "C19A50693")
    assert [r.external_case_code for r in hit] == ["C19A50693"]
    assert evidence_rows_matching_exact_code(rows, "C19A") == []
    assert evidence_rows_matching_exact_code(rows, "c19a50693") == [
        rows[2]
    ]  # equality only; caller must pass the URL token as-is


def test_focus_row_serializer_does_not_claim_mint():
    row = SimpleNamespace(
        id=88,
        external_case_code="C19A50693",
        case_id=None,
        payment_status="closed",
        amount=1200,
        currency_code="USD",
        customer_token="HIST-CUST",
        raw_source_row={"Latest Comment": "attested"},
    )
    out = serialize_payment_evidence_focus_row(row)
    assert out["external_case_code"] == "C19A50693"
    assert out["case_id"] is None
    assert out["minted"] is False
    assert out["latest_comment"] == "attested"
