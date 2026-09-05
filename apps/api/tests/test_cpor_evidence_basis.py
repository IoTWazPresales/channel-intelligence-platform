"""evidence_basis derivation — no database."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.cpor.evidence_basis import (
    CLAIM_EVIDENCED,
    NONE,
    SOURCE_ATTESTED,
    classify_evidence_basis,
    summarize_unmatched_file,
)


def test_classify_claim_beats_attestation():
    assert (
        classify_evidence_basis(has_claim_lines=True, source_attested=True) == CLAIM_EVIDENCED
    )


def test_classify_source_attested_without_claims():
    assert classify_evidence_basis(has_claim_lines=False, source_attested=True) == SOURCE_ATTESTED


def test_classify_none():
    assert classify_evidence_basis(has_claim_lines=False, source_attested=False) == NONE


def _pay(**kwargs):
    defaults = dict(
        id=1,
        external_case_code="C99HIST",
        case_id=None,
        payment_status="closed",
        amount=120.5,
        currency_code="USD",
        customer_token="TechMart",
        evidence_json={"promotion_type_raw": "Sell out PP"},
        raw_source_row={"Case ID": "C99HIST"},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_summarize_unmatched_prefers_closed_paid_and_skips_cip_codes():
    rows = [
        _pay(id=1, external_case_code="C99HIST", payment_status="to_be_applied", amount=1),
        _pay(id=2, external_case_code="C99HIST", payment_status="paid", amount=50, currency_code="USD"),
        _pay(id=3, external_case_code="KNOWN", payment_status="closed", amount=9),
    ]
    out = summarize_unmatched_file(rows, {"KNOWN"}, limit=50)
    assert out["unmatched_file_case_count"] == 1
    assert out["unmatched_file_attested_count"] == 1
    assert out["unmatched_file_rows"][0]["evidence_basis"] == SOURCE_ATTESTED
    assert out["unmatched_file_rows"][0]["amount"] == 50.0
    assert out["unmatched_file_attested_amount_by_currency"]["USD"] == 50.0
