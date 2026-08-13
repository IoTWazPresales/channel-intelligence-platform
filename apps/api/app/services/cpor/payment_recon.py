"""BACKLOG-092 — paid vs owed recon (distributor payment evidence vs case support).

Owed (interim) = Σ non-voided line ``ttl_support`` in case currency.
Paid = Σ linked ``cpor_payment_evidence.amount`` whose mapped ``payment_status``
is paid / processed / closed.
Never invent owed from ``result_qty × support_unit``.
Never silent-convert FX — FLAG ``currency_mismatch`` and keep other-currency paid aside.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.cpor_payment import CporPaymentEvidence
from app.models.dimensions import DimCustomer
from app.services.cpor.pivot import is_voided_line

PAID_STATUSES = frozenset({"paid", "processed", "closed"})
INELIGIBLE_CASE_STATUSES = frozenset({"cancelled", "rejected", "superseded"})


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _line_ttl_in_case_currency(line: Any, case_ccy: str) -> float | None:
    """Stored ttl_support (ZAR) or ttl_support_usd — never qty × support_unit."""
    if case_ccy == "USD":
        return _f(getattr(line, "ttl_support_usd", None))
    return _f(getattr(line, "ttl_support", None))


def _case_ineligible_for_owed(case: Any) -> bool:
    """Cancelled/rejected status, or soft-superseded via FK (status stays approved)."""
    status = str(getattr(case, "status", None) or "").lower()
    if status in INELIGIBLE_CASE_STATUSES:
        return True
    return getattr(case, "superseded_by_case_id", None) is not None


def _file_owed_from_evidence(ev: Any) -> float | None:
    blob = getattr(ev, "evidence_json", None) or {}
    if not isinstance(blob, dict):
        return None
    if blob.get("owed_amount_file") is not None:
        return _f(blob.get("owed_amount_file"))
    flags = blob.get("flags") or {}
    if isinstance(flags, dict) and flags.get("owed_amount_file") is not None:
        return _f(flags.get("owed_amount_file"))
    return None


def compute_case_payment_recon(
    *,
    case: Any,
    lines: list[Any],
    evidence: list[Any],
    customer: Any | None = None,
) -> dict[str, Any]:
    """Pure recon math. ``case`` / ``lines`` / ``evidence`` are duck-typed."""
    flags: list[str] = []
    case_ccy = str(getattr(case, "currency_code", None) or "ZAR").upper()

    owed: float | None = None
    if _case_ineligible_for_owed(case):
        flags.append("owed_unknown")
        flags.append("case_ineligible")
    else:
        ttl_vals: list[float] = []
        missing = 0
        for line in lines:
            if is_voided_line(line):
                continue
            ttl = _line_ttl_in_case_currency(line, case_ccy)
            if ttl is None:
                missing += 1
                continue
            ttl_vals.append(ttl)
        if not ttl_vals:
            flags.append("owed_unknown")
        else:
            owed = round(sum(ttl_vals), 4)
            if missing:
                flags.append("partial_ttl_support")

    paid_same = 0.0
    paid_other = 0.0
    other_ccys: set[str] = set()
    last_paid: date | None = None
    latest_any_status: str | None = None
    latest_any_sort: tuple[str, int] = ("", -1)
    cn_ids: list[str] = []
    paid_row_count = 0
    pending_row_count = 0
    file_owed_vals: list[float] = []

    for ev in evidence:
        ev_id = int(getattr(ev, "id", 0) or 0)
        st = str(getattr(ev, "payment_status", None) or "").lower() or None
        amt = _f(getattr(ev, "amount", None))
        ccy = str(getattr(ev, "currency_code", None) or "ZAR").upper()
        pd = getattr(ev, "payment_date", None)
        pd_key = pd.isoformat() if hasattr(pd, "isoformat") else str(pd or "")
        sort_key = (pd_key, ev_id)
        if sort_key > latest_any_sort:
            latest_any_sort = sort_key
            latest_any_status = st

        file_owed = _file_owed_from_evidence(ev)
        if file_owed is not None:
            file_owed_vals.append(file_owed)

        if st in PAID_STATUSES and amt is not None:
            paid_row_count += 1
            cn = getattr(ev, "credit_note_id", None)
            if cn:
                cn_ids.append(str(cn))
            if pd is not None:
                if last_paid is None or pd > last_paid:
                    last_paid = pd
            if ccy == case_ccy:
                paid_same += amt
            else:
                paid_other += amt
                other_ccys.add(ccy)
                flags.append("currency_mismatch")
        else:
            pending_row_count += 1

    flags = list(dict.fromkeys(flags))

    owed_amount_file: float | None = None
    if file_owed_vals:
        uniq = {round(v, 4) for v in file_owed_vals}
        if len(uniq) == 1:
            owed_amount_file = uniq.pop()
        else:
            flags.append("owed_file_inconsistent")

    paid_amount = round(paid_same, 4)
    outstanding = round(owed - paid_same, 4) if owed is not None else None

    if "owed_unknown" in flags:
        recon_status = "owed_unknown"
    elif "currency_mismatch" in flags:
        recon_status = "fx_undeclared"
    elif outstanding is None:
        recon_status = "no_owed"
    elif outstanding > 0.005:
        recon_status = "outstanding"
    elif outstanding < -0.005:
        recon_status = "overpaid"
    else:
        recon_status = "cleared"

    explanations = [
        {
            "field": "owed_amount",
            "source": "cpor_case_line.ttl_support",
            "rule": (
                f"Sum of non-voided line ttl_support in case currency {case_ccy}. "
                "Never result_qty × support_unit. Cancelled/rejected/superseded → owed_unknown."
            ),
        },
        {
            "field": "paid_amount",
            "source": "cpor_payment_evidence.amount",
            "rule": (
                "Sum of linked evidence amounts whose payment_status is paid, processed, or closed, "
                f"in case currency {case_ccy} only."
            ),
        },
        {
            "field": "outstanding_amount",
            "source": "owed_amount − paid_amount",
            "rule": "Same-currency only. Other-currency paid is flagged, never converted.",
        },
    ]
    if owed_amount_file is not None:
        explanations.append(
            {
                "field": "owed_amount_file",
                "source": "cpor_payment_evidence.evidence_json.owed_amount_file",
                "rule": "Tenant-file owed/outstanding column. Shown vs CIP owed; never replaces it.",
            }
        )

    last_iso = last_paid.isoformat() if hasattr(last_paid, "isoformat") else (str(last_paid) if last_paid else None)
    unique_cns = list(dict.fromkeys(cn_ids))

    return {
        "case_id": getattr(case, "id", None),
        "case_code": getattr(case, "case_code", None),
        "customer_id": getattr(case, "customer_id", None),
        "customer_code": getattr(customer, "code", None) if customer is not None else None,
        "customer_name": getattr(customer, "name", None) if customer is not None else None,
        "case_status": getattr(case, "status", None),
        "currency_code": case_ccy,
        "owed_amount": owed,
        "paid_amount": paid_amount,
        "paid_other_currency_amount": round(paid_other, 4) if paid_other else None,
        "paid_other_currencies": sorted(other_ccys),
        "outstanding_amount": outstanding,
        "owed_amount_file": owed_amount_file,
        "last_payment_date": last_iso,
        "credit_note_ids": unique_cns,
        "payment_evidence_count": len(evidence),
        "paid_row_count": paid_row_count,
        "pending_row_count": pending_row_count,
        "latest_payment_status": latest_any_status,
        "flags": flags,
        "recon_status": recon_status,
        "explanations": explanations,
    }


def load_payment_recon_by_case_id(
    session: Session,
    cases: list[CporCase],
    *,
    customers: dict[int, DimCustomer] | None = None,
) -> dict[int, dict[str, Any]]:
    """Batch recon for a page of cases. Dedupes evidence by id; links via case_id then code."""
    if not cases:
        return {}
    ids = [c.id for c in cases]
    codes = [c.case_code for c in cases]
    id_set = set(ids)
    code_to_id = {c.case_code: c.id for c in cases}

    lines = list(session.scalars(select(CporCaseLine).where(CporCaseLine.case_id.in_(ids))).all())
    lines_by: dict[int, list[CporCaseLine]] = defaultdict(list)
    for ln in lines:
        lines_by[ln.case_id].append(ln)

    evs = list(
        session.scalars(
            select(CporPaymentEvidence).where(
                or_(
                    CporPaymentEvidence.case_id.in_(ids),
                    CporPaymentEvidence.external_case_code.in_(codes),
                )
            )
        ).all()
    )
    ev_by: dict[int, list[CporPaymentEvidence]] = defaultdict(list)
    seen: dict[int, set[int]] = defaultdict(set)
    for ev in evs:
        cid: int | None
        if ev.case_id is not None:
            cid = ev.case_id if ev.case_id in id_set else None
        else:
            cid = code_to_id.get(ev.external_case_code)
        if cid is None:
            continue
        if ev.id in seen[cid]:
            continue
        seen[cid].add(ev.id)
        ev_by[cid].append(ev)

    cust_map = customers or {}
    out: dict[int, dict[str, Any]] = {}
    for case in cases:
        cust = cust_map.get(case.customer_id)
        out[case.id] = compute_case_payment_recon(
            case=case,
            lines=lines_by.get(case.id) or [],
            evidence=ev_by.get(case.id) or [],
            customer=cust,
        )
    return out
