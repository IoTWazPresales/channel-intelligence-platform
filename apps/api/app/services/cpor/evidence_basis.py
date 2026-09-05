"""Case evidence_basis — derived, not stored.

claim_evidenced   — at least one cpor_claim_evidence_line
source_attested   — exact Case ID match to pending-report payment evidence with closed/paid
none              — neither

Never writes claim lines. Never mints cpor_case. Unmatched file rows already live on
cpor_payment_evidence.case_id (nullable) with raw_source_row preserved.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporClaimEvidenceLine
from app.models.cpor_payment import CporPaymentEvidence

CLAIM_EVIDENCED = "claim_evidenced"
SOURCE_ATTESTED = "source_attested"
NONE = "none"
EVIDENCE_BASES = frozenset({CLAIM_EVIDENCED, SOURCE_ATTESTED, NONE})

# Operator: closed/paid attestation. processed/cn_sent are not paid.
SOURCE_ATTESTED_PAYMENT_STATUSES = frozenset({"closed", "paid"})


def classify_evidence_basis(*, has_claim_lines: bool, source_attested: bool) -> str:
    if has_claim_lines:
        return CLAIM_EVIDENCED
    if source_attested:
        return SOURCE_ATTESTED
    return NONE


def load_claim_case_ids(session: Session, case_ids: list[int] | None = None) -> set[int]:
    stmt = select(CporClaimEvidenceLine.case_id).distinct()
    if case_ids is not None:
        if not case_ids:
            return set()
        stmt = stmt.where(CporClaimEvidenceLine.case_id.in_(case_ids))
    return {int(cid) for cid in session.scalars(stmt).all() if cid is not None}


def load_source_attested_case_codes(session: Session) -> set[str]:
    codes = session.scalars(
        select(CporPaymentEvidence.external_case_code)
        .where(CporPaymentEvidence.payment_status.in_(tuple(SOURCE_ATTESTED_PAYMENT_STATUSES)))
        .distinct()
    ).all()
    return {str(c).strip() for c in codes if c and str(c).strip()}


def load_evidence_basis_by_case(
    session: Session,
    cases: Iterable[CporCase],
    *,
    claim_ids: set[int] | None = None,
    attested_codes: set[str] | None = None,
) -> dict[int, str]:
    case_list = list(cases)
    ids = [int(c.id) for c in case_list]
    claims = claim_ids if claim_ids is not None else load_claim_case_ids(session, ids)
    attested = attested_codes if attested_codes is not None else load_source_attested_case_codes(session)
    out: dict[int, str] = {}
    for case in case_list:
        code = (case.case_code or "").strip()
        out[int(case.id)] = classify_evidence_basis(
            has_claim_lines=int(case.id) in claims,
            source_attested=code in attested,
        )
    return out


def evidence_basis_counts(by_case: dict[int, str]) -> dict[str, int]:
    counts = {CLAIM_EVIDENCED: 0, SOURCE_ATTESTED: 0, NONE: 0}
    for basis in by_case.values():
        counts[basis] = counts.get(basis, 0) + 1
    return counts


def empty_basis_money() -> dict[str, Any]:
    return {"case_count": 0, "owed": 0.0, "paid": 0.0, "outstanding": 0.0}


def summarize_unmatched_file(
    rows: Iterable[CporPaymentEvidence],
    cip_codes: set[str],
    *,
    limit: int = 200,
) -> dict[str, Any]:
    """One row per unmatched Case ID. Prefer closed/paid when several rows share a code."""
    best: dict[str, CporPaymentEvidence] = {}
    for row in rows:
        code = (row.external_case_code or "").strip()
        if not code or code in cip_codes:
            continue
        prev = best.get(code)
        attested = (row.payment_status or "").strip().lower() in SOURCE_ATTESTED_PAYMENT_STATUSES
        if prev is None:
            best[code] = row
            continue
        prev_attested = (prev.payment_status or "").strip().lower() in SOURCE_ATTESTED_PAYMENT_STATUSES
        if attested and not prev_attested:
            best[code] = row
    items: list[dict[str, Any]] = []
    attested_count = 0
    amount_by_currency: dict[str, float] = {}
    for code, row in sorted(best.items()):
        attested = (row.payment_status or "").strip().lower() in SOURCE_ATTESTED_PAYMENT_STATUSES
        if attested:
            attested_count += 1
            ccy = (row.currency_code or "(blank)").strip() or "(blank)"
            if row.amount is not None:
                amount_by_currency[ccy] = amount_by_currency.get(ccy, 0.0) + float(row.amount)
        ej = row.evidence_json if isinstance(row.evidence_json, dict) else {}
        items.append(
            {
                "id": row.id,
                "external_case_code": code,
                "case_id": row.case_id,
                "payment_status": row.payment_status,
                "amount": float(row.amount) if row.amount is not None else None,
                "currency_code": row.currency_code,
                "customer_token": row.customer_token,
                "window_start": ej.get("window_start"),
                "window_end": ej.get("window_end"),
                "promotion_type_raw": ej.get("promotion_type_raw"),
                "evidence_basis": SOURCE_ATTESTED if attested else NONE,
                "has_raw_source_row": bool(row.raw_source_row),
            }
        )
    return {
        "unmatched_file_case_count": len(best),
        "unmatched_file_attested_count": attested_count,
        "unmatched_file_attested_amount_by_currency": {
            k: round(v, 2) for k, v in sorted(amount_by_currency.items())
        },
        "unmatched_file_rows": items[:limit],
        "unmatched_file_amount_note": (
            "Amounts are pending-report CN/payment figures, not case ttl_support. "
            "Not mixed into support-%-of-SRP norms."
        ),
    }


def unmatched_file_evidence_rows(session: Session, *, limit: int = 500) -> list[dict[str, Any]]:
    """Persisted payment evidence whose Case ID is not a cpor_case.case_code. Queryable."""
    cip_codes = {str(c).strip() for c in session.scalars(select(CporCase.case_code)).all() if c}
    rows = list(session.scalars(select(CporPaymentEvidence)).all())
    return summarize_unmatched_file(rows, cip_codes, limit=limit)["unmatched_file_rows"]
