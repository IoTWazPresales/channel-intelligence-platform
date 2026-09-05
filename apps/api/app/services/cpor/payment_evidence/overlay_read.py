"""Read model over applied cpor_payment_evidence — not a writer.

Exact Case ID match only. Latest Comment is read from raw_source_row so already-loaded
jobs surface dispute text even when description was mapped from Subject.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase
from app.models.cpor_payment import CporPaymentEvidence
from app.services.cpor.payment_evidence.profile_defaults import normalize_header

PENDING_PAYMENT_STATUSES = frozenset({"to_be_applied", "to_be_clarified", "processed"})


def raw_lookup(raw: dict[str, Any] | None, *aliases: str) -> str | None:
    """First non-empty raw_source_row value whose header matches an alias (newline-tolerant)."""
    if not isinstance(raw, dict):
        return None
    index = {normalize_header(str(k)): k for k in raw}
    for alias in aliases:
        src_key = index.get(normalize_header(alias))
        if src_key is None:
            continue
        value = raw.get(src_key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def latest_comment_from_raw(raw: dict[str, Any] | None) -> str | None:
    return raw_lookup(raw, "Latest Comment", "latest comment")


def deduction_no_from_raw(raw: dict[str, Any] | None) -> str | None:
    return raw_lookup(raw, "Deduction No")


def cn_status_from_raw(raw: dict[str, Any] | None) -> str | None:
    return raw_lookup(raw, "CN Status")


def cn_closed_date_from_raw(raw: dict[str, Any] | None) -> str | None:
    return raw_lookup(raw, "CN Closed Date")


def _is_pending(status: str | None) -> bool:
    if status is None or str(status).strip() == "":
        return True
    return str(status).strip().lower() in PENDING_PAYMENT_STATUSES


def build_payment_evidence_overlay(session: Session) -> dict[str, Any]:
    """Live Payments-lens figures from applied evidence. Does not write."""
    cip_codes = [c for c in session.scalars(select(CporCase.case_code)).all() if c]
    cip_set = set(cip_codes)
    rows = list(session.scalars(select(CporPaymentEvidence)).all())

    file_codes = {r.external_case_code for r in rows if r.external_case_code}
    matched = sorted(cip_set & file_codes)
    unmatched_cip = sorted(cip_set - file_codes)
    unmatched_file = sorted(file_codes - cip_set)

    status_counts: dict[str, int] = {}
    pending: list[dict[str, Any]] = []
    pending_with_comment = 0
    linked_rows = 0
    for r in rows:
        key = r.payment_status if r.payment_status else "(blank)"
        status_counts[key] = status_counts.get(key, 0) + 1
        if r.case_id is not None:
            linked_rows += 1
        if not _is_pending(r.payment_status):
            continue
        comment = latest_comment_from_raw(r.raw_source_row) or None
        if comment:
            pending_with_comment += 1
        pending.append(
            {
                "id": r.id,
                "external_case_code": r.external_case_code,
                "case_id": r.case_id,
                "payment_status": r.payment_status,
                "latest_comment": comment,
                "deduction_no": deduction_no_from_raw(r.raw_source_row),
                "cn_no": (r.credit_note_id or None),
                "cn_status": cn_status_from_raw(r.raw_source_row),
                "cn_closed_date": cn_closed_date_from_raw(r.raw_source_row),
                "amount": float(r.amount) if r.amount is not None else None,
                "currency_code": r.currency_code,
                "description": r.description,
            }
        )

    pending.sort(key=lambda x: (x["payment_status"] or "", x["external_case_code"] or ""))
    cip_n = len(cip_set)
    return {
        "row_count": len(rows),
        "distinct_file_case_codes": len(file_codes),
        "cip_case_count": cip_n,
        "matched_cip_case_count": len(matched),
        "unmatched_cip_case_count": len(unmatched_cip),
        "unmatched_file_case_count": len(unmatched_file),
        "match_rate": round(len(matched) / cip_n, 4) if cip_n else None,
        "linked_row_count": linked_rows,
        "unlinked_row_count": len(rows) - linked_rows,
        "status_counts": status_counts,
        "pending_row_count": len(pending),
        "pending_with_comment_count": pending_with_comment,
        "pending_rows": pending,
        "unmatched_cip_sample": unmatched_cip[:20],
        "unmatched_file_sample": unmatched_file[:20],
        "match_rule": "exact case_code == Case ID; no fuzzy; unmatched stays reviewable",
        "not_claim_evidence": True,
        "not_budget_ledger": True,
        "paid_note": (
            "Paid on the ZAR open book only sums linked evidence in the case currency. "
            "This ASUS pending report is almost all USD, so it does not move R0 paid / R6.0m outstanding."
        ),
    }
