"""Deterministic resolve for payment staging — case link + customer/distributor tokens."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.cpor import CporCase
from app.models.cpor_payment import ImportCporPaymentStagingLine
from app.models.dimensions import DimCustomer, DimDistributor


def _norm(s: str | None) -> str:
    return " ".join(str(s or "").strip().lower().split())


def resolve_payment_staging(db: Session, import_job_id: int) -> dict[str, Any]:
    """Link existing cases by case_code; exact unique customer/distributor name|code match."""
    lines = list(
        db.scalars(
            select(ImportCporPaymentStagingLine).where(
                ImportCporPaymentStagingLine.import_job_id == import_job_id
            )
        ).all()
    )
    if not lines:
        return {"linked_cases": 0, "customers": 0, "distributors": 0}

    case_codes = {ln.external_case_code for ln in lines if ln.external_case_code}
    cases = {
        c.case_code: c.id
        for c in db.scalars(select(CporCase).where(CporCase.case_code.in_(list(case_codes)))).all()
    }

    cust_tokens = {_norm(ln.customer_token) for ln in lines if ln.customer_token}
    dist_tokens = {_norm(ln.distributor_token) for ln in lines if ln.distributor_token}

    cust_by_token: dict[str, int] = {}
    if cust_tokens:
        customers = db.scalars(select(DimCustomer)).all()
        buckets: dict[str, list[int]] = defaultdict(list)
        for c in customers:
            for key in (_norm(c.code), _norm(c.name)):
                if key and key in cust_tokens:
                    buckets[key].append(c.id)
        for tok, ids in buckets.items():
            uniq = sorted(set(ids))
            if len(uniq) == 1:
                cust_by_token[tok] = uniq[0]

    dist_by_token: dict[str, int] = {}
    if dist_tokens:
        dists = db.scalars(select(DimDistributor)).all()
        buckets_d: dict[str, list[int]] = defaultdict(list)
        for d in dists:
            for key in (_norm(d.code), _norm(d.name)):
                if key and key in dist_tokens:
                    buckets_d[key].append(d.id)
        for tok, ids in buckets_d.items():
            uniq = sorted(set(ids))
            if len(uniq) == 1:
                dist_by_token[tok] = uniq[0]

    linked = cust_n = dist_n = 0
    for ln in lines:
        flags = dict(ln.flags_json or {})
        cid = cases.get(ln.external_case_code)
        if cid is not None:
            ln.linked_case_id = cid
            linked += 1
            flags.pop("case_unlinked", None)
        else:
            ln.linked_case_id = None
            flags["case_unlinked"] = True

        if ln.customer_token:
            rid = cust_by_token.get(_norm(ln.customer_token))
            if rid is not None:
                ln.resolved_customer_id = rid
                cust_n += 1
                flags.pop("customer_unresolved", None)
            else:
                flags["customer_unresolved"] = True
        if ln.distributor_token:
            rid = dist_by_token.get(_norm(ln.distributor_token))
            if rid is not None:
                ln.resolved_distributor_id = rid
                dist_n += 1
                flags.pop("distributor_unresolved", None)
            else:
                flags["distributor_unresolved"] = True
        ln.flags_json = flags

    db.flush()
    return {"linked_cases": linked, "customers": cust_n, "distributors": dist_n}


def map_payment_token(
    db: Session,
    *,
    import_job_id: int,
    entity: str,
    token: str,
    entity_id: int,
    create_shell_case: bool | None = None,
) -> dict[str, Any]:
    """Steward map customer/distributor token; optionally mark rows for shell-case create."""
    entity = entity.strip().lower()
    token_n = _norm(token)
    if entity not in {"customer", "distributor"}:
        raise ValueError("entity must be customer or distributor")

    q = select(ImportCporPaymentStagingLine).where(
        ImportCporPaymentStagingLine.import_job_id == import_job_id
    )
    lines = list(db.scalars(q).all())
    matched = 0
    for ln in lines:
        if entity == "customer" and _norm(ln.customer_token) == token_n:
            ln.resolved_customer_id = entity_id
            flags = dict(ln.flags_json or {})
            flags.pop("customer_unresolved", None)
            if create_shell_case is not None:
                ln.create_shell_case = bool(create_shell_case)
            ln.flags_json = flags
            matched += 1
        elif entity == "distributor" and _norm(ln.distributor_token) == token_n:
            ln.resolved_distributor_id = entity_id
            flags = dict(ln.flags_json or {})
            flags.pop("distributor_unresolved", None)
            ln.flags_json = flags
            matched += 1
    db.flush()
    return {"matched_rows": matched, "entity": entity, "token": token, "entity_id": entity_id}


def list_unresolved_payment_tokens(
    db: Session, *, import_job_id: int, entity: str
) -> list[dict[str, Any]]:
    entity = entity.strip().lower()
    lines = list(
        db.scalars(
            select(ImportCporPaymentStagingLine).where(
                ImportCporPaymentStagingLine.import_job_id == import_job_id
            )
        ).all()
    )
    buckets: dict[str, dict[str, Any]] = {}
    for ln in lines:
        if entity == "customer":
            tok = (ln.customer_token or "").strip()
            if not tok or ln.resolved_customer_id is not None:
                continue
            key = _norm(tok)
            b = buckets.setdefault(key, {"token": tok, "row_count": 0, "sample_case_codes": []})
            b["row_count"] += 1
            if len(b["sample_case_codes"]) < 5 and ln.external_case_code not in b["sample_case_codes"]:
                b["sample_case_codes"].append(ln.external_case_code)
        elif entity == "distributor":
            tok = (ln.distributor_token or "").strip()
            if not tok or ln.resolved_distributor_id is not None:
                continue
            key = _norm(tok)
            b = buckets.setdefault(key, {"token": tok, "row_count": 0, "sample_case_codes": []})
            b["row_count"] += 1
            if len(b["sample_case_codes"]) < 5 and ln.external_case_code not in b["sample_case_codes"]:
                b["sample_case_codes"].append(ln.external_case_code)
        elif entity == "case":
            if ln.linked_case_id is not None:
                continue
            tok = ln.external_case_code
            key = _norm(tok)
            b = buckets.setdefault(
                key,
                {
                    "token": tok,
                    "row_count": 0,
                    "create_shell_case": bool(ln.create_shell_case),
                    "resolved_customer_id": ln.resolved_customer_id,
                    "window_start": ln.window_start.isoformat() if ln.window_start else None,
                    "window_end": ln.window_end.isoformat() if ln.window_end else None,
                    "promotion_type_raw": ln.promotion_type_raw,
                },
            )
            b["row_count"] += 1
            if ln.create_shell_case:
                b["create_shell_case"] = True
            if ln.resolved_customer_id is not None:
                b["resolved_customer_id"] = ln.resolved_customer_id
    return sorted(buckets.values(), key=lambda x: (-int(x["row_count"]), str(x["token"])))


def mark_shell_case_for_code(
    db: Session, *, import_job_id: int, case_code: str, enabled: bool = True
) -> int:
    """Steward: allow apply to create a shell cpor_case for this external case code."""
    result = db.execute(
        update(ImportCporPaymentStagingLine)
        .where(
            ImportCporPaymentStagingLine.import_job_id == import_job_id,
            ImportCporPaymentStagingLine.external_case_code == case_code,
            ImportCporPaymentStagingLine.linked_case_id.is_(None),
        )
        .values(create_shell_case=enabled)
    )
    db.flush()
    return int(result.rowcount or 0)


def payment_job_summary(db: Session, import_job_id: int) -> dict[str, Any]:
    lines = list(
        db.scalars(
            select(ImportCporPaymentStagingLine).where(
                ImportCporPaymentStagingLine.import_job_id == import_job_id
            )
        ).all()
    )
    return {
        "row_count": len(lines),
        "linked_case_count": sum(1 for ln in lines if ln.linked_case_id is not None),
        "unlinked_case_count": sum(1 for ln in lines if ln.linked_case_id is None),
        "shell_marked_count": sum(1 for ln in lines if ln.create_shell_case),
        "customer_resolved_count": sum(1 for ln in lines if ln.resolved_customer_id is not None),
        "customer_unresolved_count": sum(
            1 for ln in lines if ln.customer_token and ln.resolved_customer_id is None
        ),
        "distributor_resolved_count": sum(1 for ln in lines if ln.resolved_distributor_id is not None),
        "distributor_unresolved_count": sum(
            1 for ln in lines if ln.distributor_token and ln.resolved_distributor_id is None
        ),
        "distinct_case_codes": len({ln.external_case_code for ln in lines}),
        "amount_sum": float(
            sum((ln.amount or 0) for ln in lines)  # type: ignore[arg-type]
        ),
    }
