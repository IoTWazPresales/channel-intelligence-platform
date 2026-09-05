"""Tests for A2-04 norms + A2-05 comparable ranking."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.norms_and_comparable import (
    build_comparable_cases,
    build_support_norms,
    normalize_quarter_label,
    trailing_quarter_labels,
)


def test_normalize_quarter_variants() -> None:
    assert normalize_quarter_label("2025Q2") == "2025Q2"
    assert normalize_quarter_label("25Q2") == "2025Q2"
    assert normalize_quarter_label("26Q1") == "2026Q1"
    assert normalize_quarter_label(None, fallback=date(2024, 5, 1)) == "2024Q2"


def test_trailing_quarters() -> None:
    assert trailing_quarter_labels("2025Q2", 4) == ["2025Q2", "2025Q1", "2024Q4", "2024Q3"]


def _line(**kwargs):
    defaults = dict(
        product_id=1,
        estimate_qty=10.0,
        result_qty=8.0,
        ttl_support=100.0,
        ttl_support_usd=5.0,
        support_unit=50.0,
        srp=500.0,
        pod_quarter="2025Q2",
        remark=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_norms_absolute_and_pct(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.cpor.norms_and_comparable.load_evidence_basis_by_case",
        lambda session, cases, **k: {int(c.id): "none" for c in cases},
    )
    monkeypatch.setattr(
        "app.services.cpor.norms_and_comparable.unmatched_file_evidence_rows",
        lambda session, **k: [],
    )
    case = SimpleNamespace(
        id=1,
        customer_id=7,
        promotion_type="Sell out PP",
        superseded_by_case_id=None,
        window_start=date(2025, 4, 1),
        lines=[
            _line(pod_quarter="2025Q2", ttl_support_usd=10.0, ttl_support=180.0, support_unit=50, srp=500),
            _line(pod_quarter="2025Q1", ttl_support_usd=20.0, ttl_support=360.0, support_unit=100, srp=500),
        ],
    )
    session = MagicMock()
    scalars = MagicMock()
    scalars.unique.return_value.all.return_value = [case]
    session.scalars.return_value = scalars
    session.execute.return_value = MagicMock(
        all=MagicMock(return_value=[(7, "C1", "Cust")])
    )
    out = build_support_norms(session, trailing_quarters=4)
    assert out["anchor_quarter"] == "2025Q2"
    assert out["trailing_quarters"] == 4
    cust = out["by_customer"][0]
    assert cust["absolute_support_usd_total"] == 30.0
    assert cust["quarters_present"] == 2
    assert abs(cust["support_pct_of_srp_avg"] - 0.15) < 1e-9  # (0.1 + 0.2) / 2
    assert out["attested_unmatched_file"]["case_count"] == 0


def test_comparable_ranks_same_customer_first(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.cpor.norms_and_comparable.load_evidence_basis_by_case",
        lambda session, cases, **k: {int(c.id): "none" for c in cases},
    )
    monkeypatch.setattr(
        "app.services.cpor.norms_and_comparable.unmatched_file_evidence_rows",
        lambda session, **k: [
            {
                "external_case_code": "CFILE1",
                "customer_token": "Alpha",
                "promotion_type_raw": "Sell out PP",
                "payment_status": "paid",
                "evidence_basis": "source_attested",
                "window_start": None,
                "window_end": None,
            }
        ],
    )
    seed = SimpleNamespace(
        id=10,
        case_code="C1",
        customer_id=1,
        promotion_type="Sell out PP",
        superseded_by_case_id=None,
        window_start=date(2025, 4, 1),
        window_end=date(2025, 6, 30),
        status="settled",
        lines=[_line(product_id=1, estimate_qty=100, pod_quarter="2025Q2")],
    )
    same = SimpleNamespace(
        id=11,
        case_code="C2",
        customer_id=1,
        promotion_type="Other",
        superseded_by_case_id=None,
        window_start=date(2024, 4, 1),
        window_end=date(2024, 6, 30),
        status="settled",
        lines=[_line(product_id=1, estimate_qty=90, pod_quarter="2024Q2")],
    )
    other = SimpleNamespace(
        id=12,
        case_code="C3",
        customer_id=2,
        promotion_type="Sell out PP",
        superseded_by_case_id=None,
        window_start=date(2025, 4, 1),
        window_end=date(2025, 6, 30),
        status="settled",
        lines=[_line(product_id=1, estimate_qty=100, pod_quarter="2025Q2")],
    )
    session = MagicMock()
    scalars = MagicMock()
    scalars.unique.return_value.all.return_value = [seed, same, other]
    session.scalars.return_value = scalars
    session.get.return_value = seed
    session.execute.side_effect = [
        MagicMock(all=MagicMock(return_value=[(1, "NB")])),
        MagicMock(all=MagicMock(return_value=[(1, "A", "Alpha"), (2, "B", "Beta")])),
    ]
    out = build_comparable_cases(session, case_id=10, limit=10)
    assert out["items"][0]["case_id"] == 11
    assert out["items"][0]["rank_axes"]["same_customer"] is True
    assert out["items"][1]["case_id"] == 12
    file_item = next(r for r in out["items"] if r["case_id"] is None)
    assert file_item["case_code"] == "CFILE1"
    assert file_item["evidence_basis"] == "source_attested"
