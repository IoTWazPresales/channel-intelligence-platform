"""NS-4 Settlement book read model — regime figures, shape segments, concentration."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.cpor import CporCase
from app.models.dimensions import DimCustomer
from app.services.cpor.evidence_basis import (
    CLAIM_EVIDENCED,
    NONE,
    SOURCE_ATTESTED,
    empty_basis_money,
    load_evidence_basis_by_case,
)
from app.services.cpor.payment_recon import INELIGIBLE_CASE_STATUSES, load_payment_recon_by_case_id
from app.services.cpor.settle_readiness import build_settle_readiness, settle_fx_blocked


def _empty_basis_breakdown() -> dict[str, dict[str, Any]]:
    return {
        CLAIM_EVIDENCED: empty_basis_money(),
        SOURCE_ATTESTED: empty_basis_money(),
        NONE: empty_basis_money(),
    }


def _f(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def shape_segment_pcts(
    *,
    book_total: float,
    settled_amount: float,
    outstanding_amount: float,
    blocked_amount: float,
) -> dict[str, float]:
    """Partition the book: paid | unblocked outstanding | FX-blocked outstanding.

    Blocked is a subset of outstanding, never a third addend. When some open cases have
    negative ttl_support, blocked (positive outstanding only) can exceed book_total;
    the bar still cannot exceed the track — blocked is capped at max(outstanding, 0).
    """
    denom = book_total if book_total > 0 else 1.0
    blocked_capped = min(max(blocked_amount, 0.0), max(outstanding_amount, 0.0))
    unblocked = max(0.0, max(outstanding_amount, 0.0) - blocked_capped)
    return {
        "settled_pct": round((settled_amount / denom) * 100, 1),
        "outstanding_pct": round((unblocked / denom) * 100, 1),
        "blocked_pct": round((blocked_capped / denom) * 100, 1),
    }


def build_settlement_book_read_model(session: Session) -> dict[str, Any]:
    """Aggregate book-level owed / paid / outstanding / blocked for Settlement grammar-1."""
    cases = list(
        session.scalars(
            select(CporCase)
            .where(CporCase.superseded_by_case_id.is_(None))
            .options(joinedload(CporCase.lines))
        )
        .unique()
        .all()
    )
    if not cases:
        return {
            "data_unavailable": False,
            "open_case_count": 0,
            "currency_code": "ZAR",
            "book_total": 0.0,
            "settled_amount": 0.0,
            "outstanding_amount": 0.0,
            "blocked_amount": 0.0,
            "shape_segments": {"settled_pct": 0.0, "outstanding_pct": 0.0, "blocked_pct": 0.0},
            "read_line": "No open settlement cases in book.",
            "concentration": [],
            "by_evidence_basis": _empty_basis_breakdown(),
            "evidence_basis_note": (
                "Open-book totals mix claim_evidenced, source_attested, and none. "
                "by_evidence_basis is a labeled partition of the same owed/paid/outstanding; "
                "it does not change book_total."
            ),
        }

    customer_ids = {int(c.customer_id) for c in cases if c.customer_id is not None}
    cust_rows = (
        session.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                DimCustomer.id.in_(customer_ids)
            )
        ).all()
        if customer_ids
        else []
    )
    cust_map: dict[int, Any] = {}
    for r in cust_rows:
        cust_map[int(r[0])] = type("Cust", (), {"id": r[0], "code": r[1], "name": r[2]})()

    recon_by = load_payment_recon_by_case_id(session, cases, customers=cust_map)
    basis_by = load_evidence_basis_by_case(session, cases)

    book_total = 0.0
    settled_amount = 0.0
    outstanding_amount = 0.0
    blocked_amount = 0.0
    open_case_count = 0
    concentration: list[dict[str, Any]] = []
    by_basis = _empty_basis_breakdown()

    for case in cases:
        status = str(case.status or "").lower()
        if status in INELIGIBLE_CASE_STATUSES:
            continue
        if status == "settled":
            continue

        open_case_count += 1
        recon = recon_by.get(case.id) or {}
        owed = _f(recon.get("owed_amount"))
        paid = _f(recon.get("paid_amount"))
        outstanding = _f(recon.get("outstanding_amount"))
        if outstanding <= 0 and owed > paid:
            outstanding = max(0.0, owed - paid)

        readiness = build_settle_readiness(
            case,
            claim_row_count=int(recon.get("payment_evidence_count") or 0),
            open_assumption_count=0,
        )
        fx_blocked = settle_fx_blocked(case) or readiness.get("fx_settle_allowed") is False

        book_total += owed
        settled_amount += paid
        outstanding_amount += outstanding
        if fx_blocked and outstanding > 0:
            blocked_amount += outstanding

        basis = basis_by.get(int(case.id), NONE)
        bucket = by_basis.setdefault(basis, empty_basis_money())
        bucket["case_count"] += 1
        bucket["owed"] += owed
        bucket["paid"] += paid
        bucket["outstanding"] += outstanding

        if outstanding > 0:
            cust = cust_map.get(int(case.customer_id)) if case.customer_id else None
            concentration.append(
                {
                    "case_id": case.id,
                    "case_code": case.case_code,
                    "customer_code": getattr(cust, "code", None),
                    "customer_name": getattr(cust, "name", None),
                    "outstanding_amount": round(outstanding, 2),
                    "fx_blocked": fx_blocked,
                    "evidence_basis": basis,
                }
            )

    concentration.sort(key=lambda r: r["outstanding_amount"], reverse=True)
    concentration = concentration[:8]

    segs = shape_segment_pcts(
        book_total=book_total,
        settled_amount=settled_amount,
        outstanding_amount=outstanding_amount,
        blocked_amount=blocked_amount,
    )
    settled_pct = segs["settled_pct"]
    outstanding_pct = segs["outstanding_pct"]
    blocked_pct = segs["blocked_pct"]

    read_line = (
        f"{open_case_count} open cases · R {outstanding_amount:,.0f} outstanding"
        f" · R {settled_amount:,.0f} paid"
    )
    if blocked_amount > 0:
        read_line += f" · R {blocked_amount:,.0f} blocked on FX"

    return {
        "data_unavailable": False,
        "open_case_count": open_case_count,
        "currency_code": "ZAR",
        "book_total": round(book_total, 2),
        "settled_amount": round(settled_amount, 2),
        "outstanding_amount": round(outstanding_amount, 2),
        "blocked_amount": round(blocked_amount, 2),
        "shape_segments": {
            "settled_pct": settled_pct,
            "outstanding_pct": outstanding_pct,
            "blocked_pct": blocked_pct,
        },
        "read_line": read_line,
        "concentration": concentration,
        "by_evidence_basis": {
            k: {
                "case_count": int(v["case_count"]),
                "owed": round(v["owed"], 2),
                "paid": round(v["paid"], 2),
                "outstanding": round(v["outstanding"], 2),
            }
            for k, v in by_basis.items()
        },
        "evidence_basis_note": (
            "Open-book totals mix claim_evidenced, source_attested, and none. "
            "by_evidence_basis partitions the same owed/paid/outstanding; book_total is unchanged."
        ),
    }
