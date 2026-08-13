"""BACKLOG-092 paid vs owed recon — pure math (no DB)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.services.cpor.payment_recon import compute_case_payment_recon


def _case(**kwargs):
    base = dict(
        id=1,
        case_code="C1",
        customer_id=9,
        status="approved",
        currency_code="ZAR",
        superseded_by_case_id=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _line(*, ttl_support=None, ttl_support_usd=None, remark="", estimate_qty=10):
    return SimpleNamespace(
        ttl_support=ttl_support,
        ttl_support_usd=ttl_support_usd,
        remark=remark,
        estimate_qty=estimate_qty,
    )


def _ev(**kwargs):
    base = dict(
        id=1,
        amount=100.0,
        currency_code="ZAR",
        payment_status="closed",
        payment_date=date(2026, 8, 1),
        credit_note_id="CN1",
        evidence_json={},
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_owed_is_ttl_support_not_qty_times_unit():
    case = _case()
    lines = [_line(ttl_support=1234.0, estimate_qty=10)]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=[])
    assert out["owed_amount"] == 1234.0
    assert out["paid_amount"] == 0.0
    assert out["outstanding_amount"] == 1234.0
    assert out["recon_status"] == "outstanding"


def test_no_ttl_flags_owed_unknown_does_not_invent():
    case = _case(status="approved")
    lines = [_line(ttl_support=None, estimate_qty=20)]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=[_ev(amount=50)])
    assert out["owed_amount"] is None
    assert "owed_unknown" in out["flags"]
    assert out["outstanding_amount"] is None
    assert out["paid_amount"] == 50.0


def test_cancelled_case_owed_unknown():
    case = _case(status="cancelled")
    lines = [_line(ttl_support=999.0)]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=[])
    assert out["owed_amount"] is None
    assert "owed_unknown" in out["flags"]
    assert "case_ineligible" in out["flags"]


def test_superseded_by_case_id_owed_unknown_even_if_status_approved():
    """CPOR supersession is the FK, not status='superseded' (that status is not in the vocab)."""
    case = _case(status="approved", superseded_by_case_id=88)
    lines = [_line(ttl_support=999.0)]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=[])
    assert out["owed_amount"] is None
    assert "owed_unknown" in out["flags"]
    assert "case_ineligible" in out["flags"]


def test_paid_excludes_to_be_applied():
    case = _case()
    lines = [_line(ttl_support=300.0)]
    evidence = [
        _ev(id=1, amount=100.0, payment_status="closed"),
        _ev(id=2, amount=80.0, payment_status="to_be_applied", credit_note_id="CN2"),
        _ev(id=3, amount=50.0, payment_status="processed", credit_note_id="CN3"),
        _ev(id=4, amount=10.0, payment_status="cn_sent", credit_note_id="CN4"),
    ]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=evidence)
    assert out["paid_amount"] == 150.0
    assert out["outstanding_amount"] == 150.0
    assert out["paid_row_count"] == 2
    assert out["pending_row_count"] == 2
    assert out["credit_note_ids"] == ["CN1", "CN3"]


def test_fx_mismatch_not_converted():
    case = _case(currency_code="ZAR")
    lines = [_line(ttl_support=200.0)]
    evidence = [
        _ev(id=1, amount=50.0, currency_code="ZAR", payment_status="paid"),
        _ev(id=2, amount=999.0, currency_code="USD", payment_status="closed", credit_note_id="CN-USD"),
    ]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=evidence)
    assert out["paid_amount"] == 50.0
    assert out["paid_other_currency_amount"] == 999.0
    assert out["paid_other_currencies"] == ["USD"]
    assert "currency_mismatch" in out["flags"]
    assert out["outstanding_amount"] == 150.0
    assert out["recon_status"] == "fx_undeclared"


def test_voided_line_excluded_from_owed():
    case = _case()
    lines = [
        _line(ttl_support=100.0, remark="[voided]"),
        _line(ttl_support=40.0, remark=""),
    ]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=[])
    assert out["owed_amount"] == 40.0


def test_file_owed_shown_not_replacing_cip():
    case = _case()
    lines = [_line(ttl_support=200.0)]
    evidence = [
        _ev(evidence_json={"owed_amount_file": 180.0}, amount=0, payment_status="to_be_applied"),
    ]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=evidence)
    assert out["owed_amount"] == 200.0
    assert out["owed_amount_file"] == 180.0
    assert out["owed_amount"] != out["owed_amount_file"]


def test_cleared_when_paid_equals_owed():
    case = _case()
    lines = [_line(ttl_support=100.0)]
    out = compute_case_payment_recon(case=case, lines=lines, evidence=[_ev(amount=100.0)])
    assert out["outstanding_amount"] == 0.0
    assert out["recon_status"] == "cleared"
