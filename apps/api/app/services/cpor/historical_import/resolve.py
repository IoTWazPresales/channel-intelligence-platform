"""Deterministic entity resolution for historical CPOR staging (never auto-create)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor_historical import ImportCporHistoricalStagingLine
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.services.cpor.claim_evidence import load_product_resolution_index, resolve_claim_product_id


def _norm(token: str | None) -> str:
    return " ".join(str(token or "").strip().upper().split())


def _load_customer_token_index(db: Session) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = defaultdict(list)
    for cid, code, name in db.execute(select(DimCustomer.id, DimCustomer.code, DimCustomer.name)).all():
        for raw in (code, name):
            key = _norm(raw)
            if key and int(cid) not in idx[key]:
                idx[key].append(int(cid))
    return idx


def _load_distributor_token_index(db: Session) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = defaultdict(list)
    for did, code, name in db.execute(
        select(DimDistributor.id, DimDistributor.code, DimDistributor.name)
    ).all():
        for raw in (code, name):
            key = _norm(raw)
            if key and int(did) not in idx[key]:
                idx[key].append(int(did))
    return idx


def resolve_staging_entities(db: Session, *, job_id: int) -> dict[str, Any]:
    """Fill resolved_*_id where an exact single match exists. Never creates dims."""
    rows = list(
        db.scalars(
            select(ImportCporHistoricalStagingLine).where(
                ImportCporHistoricalStagingLine.import_job_id == job_id
            )
        ).all()
    )
    if not rows:
        return {"rows": 0, "products_resolved": 0, "customers_resolved": 0, "distributors_resolved": 0}

    product_index = load_product_resolution_index(db)
    customers = _load_customer_token_index(db)
    distributors = _load_distributor_token_index(db)

    p_n = c_n = d_n = 0
    for row in rows:
        if row.resolved_product_id is None and row.sales_model_token:
            pid, _tok, status = resolve_claim_product_id(
                product_index, sales_model=row.sales_model_token
            )
            if status == "resolved" and pid is not None:
                row.resolved_product_id = pid
                p_n += 1

        if row.resolved_customer_id is None and row.customer_token:
            ids = customers.get(_norm(row.customer_token)) or []
            if len(ids) == 1:
                row.resolved_customer_id = ids[0]
                c_n += 1

        if row.resolved_distributor_id is None and row.distributor_token:
            ids = distributors.get(_norm(row.distributor_token)) or []
            if len(ids) == 1:
                row.resolved_distributor_id = ids[0]
                d_n += 1

    db.flush()
    return {
        "rows": len(rows),
        "products_resolved": p_n,
        "customers_resolved": c_n,
        "distributors_resolved": d_n,
    }


def map_staging_token(
    db: Session,
    *,
    job_id: int,
    entity: str,
    token: str,
    dim_id: int,
) -> int:
    """Steward map: set resolved_*_id for all staging rows matching token. Returns updated count."""
    return map_staging_tokens(db, job_id=job_id, entity=entity, tokens=[token], dim_id=dim_id)


def map_staging_tokens(
    db: Session,
    *,
    job_id: int,
    entity: str,
    tokens: list[str],
    dim_id: int,
) -> int:
    """Bulk steward map: one dim_id applied to many tokens of the same entity."""
    entity_l = entity.strip().lower()
    wanted = {_norm(t) for t in tokens if (t or "").strip()}
    if not wanted:
        return 0

    q = select(ImportCporHistoricalStagingLine).where(
        ImportCporHistoricalStagingLine.import_job_id == job_id
    )
    rows = list(db.scalars(q).all())
    updated = 0
    for row in rows:
        if entity_l == "product" and _norm(row.sales_model_token) in wanted:
            row.resolved_product_id = dim_id
            updated += 1
        elif entity_l == "customer" and _norm(row.customer_token) in wanted:
            row.resolved_customer_id = dim_id
            updated += 1
        elif entity_l == "distributor" and _norm(row.distributor_token) in wanted:
            row.resolved_distributor_id = dim_id
            updated += 1
    db.flush()
    return updated


def list_unresolved_candidates(db: Session, *, job_id: int) -> dict[str, list[dict[str, Any]]]:
    """Group unresolved tokens for steward workspace tabs."""
    rows = list(
        db.scalars(
            select(ImportCporHistoricalStagingLine).where(
                ImportCporHistoricalStagingLine.import_job_id == job_id,
                ImportCporHistoricalStagingLine.skip_apply.is_(False),
            )
        ).all()
    )
    products: dict[str, int] = defaultdict(int)
    customers: dict[str, int] = defaultdict(int)
    distributors: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.sales_model_token and row.resolved_product_id is None:
            products[str(row.sales_model_token).strip()] += 1
        if row.customer_token and row.resolved_customer_id is None:
            customers[str(row.customer_token).strip()] += 1
        if row.distributor_token and row.resolved_distributor_id is None:
            distributors[str(row.distributor_token).strip()] += 1

    def _pack(d: dict[str, int], entity: str) -> list[dict[str, Any]]:
        return [
            {
                "entity": entity,
                "token": tok,
                "row_count": cnt,
                "confidence": None,
                "status": "unresolved",
            }
            for tok, cnt in sorted(d.items(), key=lambda x: (-x[1], x[0].lower()))
        ]

    return {
        "product": _pack(products, "product"),
        "customer": _pack(customers, "customer"),
        "distributor": _pack(distributors, "distributor"),
    }


def case_apply_blockers(row: ImportCporHistoricalStagingLine) -> list[str]:
    """Hard blockers for a staging line's case (FLAG≠BLOCK: parity alone does not block)."""
    blockers: list[str] = []
    flags = list((row.flags_json or {}).get("flags") or [])
    for f in (
        "case_code_collision_native",
        "duplicate_line_grain",
        "missing_window",
        "missing_customer_token",
        "missing_product_token",
    ):
        if f in flags:
            blockers.append(f)
    if row.resolved_product_id is None:
        blockers.append("unresolved_product")
    if row.resolved_customer_id is None:
        blockers.append("unresolved_customer")
    if (row.distributor_token or "").strip() and row.resolved_distributor_id is None:
        blockers.append("unresolved_distributor")
    if not row.window_start or not row.window_end:
        blockers.append("missing_window")
    return sorted(set(blockers))
