"""Steward operations for customer sales import mapping candidates (sync Session).

Product mapping updates ``CustomerProductAlias`` and re-resolves matching
``fact_customer_sales`` rows.  Store mapping points rows at ``dim_store``.
Re-resolve replays product + store resolution for an entire job after alias
or Product Master changes.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer_sales import CustomerProductAlias, DimStore, FactCustomerSales
from app.models.dimensions import DimCustomer, DimProduct
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.customer_sales_import import (
    CUSTOMER_SALES_PRODUCT_ENTITY,
    _resolve_product_for_customer_sales,
    _resolve_store,
)

_CANDIDATE_TERMINAL_STATUSES = frozenset({"resolved", "steward_rejected", "ignored"})


class StewardOpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = message


def _load_candidate(db: Session, candidate_id: int) -> ImportEntityMappingCandidate:
    cand = db.get(ImportEntityMappingCandidate, int(candidate_id))
    if cand is None:
        raise StewardOpError("Candidate not found", status_code=404)
    return cand


def _assert_actionable(cand: ImportEntityMappingCandidate) -> None:
    if cand.status in _CANDIDATE_TERMINAL_STATUSES:
        raise StewardOpError(
            f"Candidate {cand.id} is already terminal (status={cand.status})",
            status_code=400,
        )


def _fact_ids_from_context(cand: ImportEntityMappingCandidate) -> list[int]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("fact_ids")
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _customer_id_from_context(cand: ImportEntityMappingCandidate) -> int | None:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    v = ctx.get("customer_id")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def execute_map_customer_sales_product(
    db: Session, candidate_id: int, product_id: int
) -> dict[str, Any]:
    """Map an article code to a product via CustomerProductAlias and update matching fact rows."""
    cand = _load_candidate(db, candidate_id)
    if cand.entity_type != CUSTOMER_SALES_PRODUCT_ENTITY:
        raise StewardOpError("Not a customer_sales_product candidate", status_code=400)
    _assert_actionable(cand)

    product = db.get(DimProduct, int(product_id))
    if not product:
        raise StewardOpError("product_id not found", status_code=404)

    customer_id = _customer_id_from_context(cand)
    normalized_key = (cand.normalized_key or "").strip().lower()
    if not normalized_key:
        raise StewardOpError("Candidate has empty normalized_key", status_code=400)

    samples = cand.sample_raw_values or []
    source_article_code = samples[0] if samples and isinstance(samples[0], str) else normalized_key

    if customer_id is not None:
        existing_alias = db.execute(
            select(CustomerProductAlias).where(
                CustomerProductAlias.customer_id == customer_id,
                CustomerProductAlias.normalized_code == normalized_key[:512],
            )
        ).scalars().first()

        if existing_alias is not None:
            existing_alias.product_id = int(product_id)
            existing_alias.status = "approved"
            db.add(existing_alias)
        else:
            alias = CustomerProductAlias(
                customer_id=customer_id,
                source_article_code=source_article_code[:512],
                normalized_code=normalized_key[:512],
                product_id=int(product_id),
                status="approved",
                notes=f"Steward mapped from candidate {cand.id} (job {cand.import_job_id})",
                created_from_import_job_id=cand.import_job_id,
            )
            db.add(alias)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                raise StewardOpError(
                    "Could not create product alias (duplicate or conflict)", status_code=409
                ) from None

    fact_ids = _fact_ids_from_context(cand)
    updated = 0
    for fid in fact_ids:
        fact = db.get(FactCustomerSales, fid)
        if fact is None:
            continue
        fact.product_id = int(product_id)
        fact.product_resolution_status = "resolved_steward"
        db.add(fact)
        updated += 1

    cand.status = "resolved"
    cand.suggested_entity_id = int(product_id)
    cand.match_reason = "steward_map_product"
    db.add(cand)
    db.commit()

    return {
        "ok": True,
        "candidate_id": int(cand.id),
        "product_id": int(product_id),
        "rows_updated": updated,
    }


def execute_create_customer_sales_product_alias(
    db: Session, candidate_id: int, product_id: int, customer_id: int
) -> dict[str, Any]:
    """Create a CustomerProductAlias from a candidate without a pre-existing alias."""
    cand = _load_candidate(db, candidate_id)
    if cand.entity_type != CUSTOMER_SALES_PRODUCT_ENTITY:
        raise StewardOpError("Not a customer_sales_product candidate", status_code=400)
    _assert_actionable(cand)

    product = db.get(DimProduct, int(product_id))
    if not product:
        raise StewardOpError("product_id not found", status_code=404)
    customer = db.get(DimCustomer, int(customer_id))
    if not customer:
        raise StewardOpError("customer_id not found", status_code=404)

    normalized_key = (cand.normalized_key or "").strip().lower()
    if not normalized_key:
        raise StewardOpError("Candidate has empty normalized_key", status_code=400)

    samples = cand.sample_raw_values or []
    source_article_code = samples[0] if samples and isinstance(samples[0], str) else normalized_key

    alias = CustomerProductAlias(
        customer_id=int(customer_id),
        source_article_code=source_article_code[:512],
        normalized_code=normalized_key[:512],
        product_id=int(product_id),
        status="approved",
        notes=f"Steward created alias from candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise StewardOpError(
            "Could not create product alias (duplicate or conflict)", status_code=409
        ) from None

    fact_ids = _fact_ids_from_context(cand)
    updated = 0
    for fid in fact_ids:
        fact = db.get(FactCustomerSales, fid)
        if fact is None:
            continue
        fact.product_id = int(product_id)
        fact.product_resolution_status = "resolved_steward"
        db.add(fact)
        updated += 1

    cand.status = "resolved"
    cand.suggested_entity_id = int(product_id)
    cand.match_reason = "steward_create_alias"
    db.add(cand)
    db.commit()
    db.refresh(alias)

    return {
        "ok": True,
        "candidate_id": int(cand.id),
        "alias_id": int(alias.id),
        "product_id": int(product_id),
        "customer_id": int(customer_id),
        "rows_updated": updated,
    }


def execute_map_customer_sales_store(
    db: Session, candidate_id: int, store_id: int
) -> dict[str, Any]:
    """Map a store code candidate to an existing dim_store."""
    cand = _load_candidate(db, candidate_id)
    _assert_actionable(cand)

    store = db.get(DimStore, int(store_id))
    if not store:
        raise StewardOpError("store_id not found", status_code=404)

    fact_ids = _fact_ids_from_context(cand)
    updated = 0
    for fid in fact_ids:
        fact = db.get(FactCustomerSales, fid)
        if fact is None:
            continue
        fact.store_id = int(store_id)
        fact.store_resolution_status = "resolved_steward"
        db.add(fact)
        updated += 1

    cand.status = "resolved"
    cand.suggested_entity_id = int(store_id)
    cand.match_reason = "steward_map_store"
    db.add(cand)
    db.commit()

    return {
        "ok": True,
        "candidate_id": int(cand.id),
        "store_id": int(store_id),
        "rows_updated": updated,
    }


def execute_create_provisional_store(
    db: Session, customer_id: int, store_code: str, store_name: str | None = None
) -> dict[str, Any]:
    """Create a new DimStore for unrecognized store codes."""
    customer = db.get(DimCustomer, int(customer_id))
    if not customer:
        raise StewardOpError("customer_id not found", status_code=404)

    sc = (store_code or "").strip()
    if not sc:
        raise StewardOpError("store_code is required", status_code=400)

    existing = db.execute(
        select(DimStore).where(
            DimStore.customer_id == int(customer_id),
            DimStore.store_code == sc,
        )
    ).scalars().first()
    if existing is not None:
        return {
            "ok": True,
            "idempotent": True,
            "store_id": int(existing.id),
            "store_code": existing.store_code,
            "customer_id": int(customer_id),
        }

    name = (store_name or "").strip() or sc
    store = DimStore(
        customer_id=int(customer_id),
        store_code=sc[:64],
        store_name=name[:256],
        store_type="provisional",
        is_active=True,
    )
    db.add(store)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise StewardOpError(
            "Could not create store (duplicate or conflict)", status_code=409
        ) from None

    db.commit()
    db.refresh(store)

    return {
        "ok": True,
        "store_id": int(store.id),
        "store_code": store.store_code,
        "customer_id": int(customer_id),
    }


def execute_reject_customer_sales_candidate(
    db: Session, candidate_id: int
) -> dict[str, Any]:
    """Mark candidate as rejected — no resolution, no auto-apply."""
    cand = _load_candidate(db, candidate_id)
    _assert_actionable(cand)

    cand.status = "steward_rejected"
    cand.match_reason = "steward_rejected"
    db.add(cand)
    db.commit()

    return {"ok": True, "candidate_id": int(cand.id), "status": cand.status}


def execute_reresolve_customer_sales_job(
    db: Session, job_id: int
) -> dict[str, Any]:
    """Re-run product and store resolution on all fact_customer_sales rows for a job.

    Used after Product Master commits or alias updates to pick up newly available mappings.
    """
    job = db.get(ImportJob, int(job_id))
    if not job:
        raise StewardOpError("job_id not found", status_code=404)

    customer_id: int | None = None
    staged = job.staged_metadata or {}
    if isinstance(staged, dict):
        cid_raw = staged.get("customer_id")
        if cid_raw is not None:
            try:
                customer_id = int(cid_raw)
            except (TypeError, ValueError):
                pass

    rows = list(
        db.execute(
            select(FactCustomerSales).where(FactCustomerSales.import_job_id == int(job_id))
        ).scalars().all()
    )

    product_updated = 0
    store_updated = 0

    for fact in rows:
        if fact.product_id is None or fact.product_resolution_status in ("no_match", "no_identifier"):
            code = (fact.source_article_code or "").strip()
            if code:
                pid, p_status, p_detail = _resolve_product_for_customer_sales(
                    db, code, customer_id or fact.customer_id
                )
                if pid is not None:
                    fact.product_id = pid
                    fact.product_resolution_status = p_status
                    db.add(fact)
                    product_updated += 1

        if fact.store_id is None or fact.store_resolution_status in ("no_match", "no_customer"):
            store_code = (fact.source_store_code or "").strip()
            if store_code:
                sid, s_status = _resolve_store(db, store_code, customer_id or fact.customer_id)
                if sid is not None:
                    fact.store_id = sid
                    fact.store_resolution_status = s_status
                    db.add(fact)
                    store_updated += 1

    db.flush()

    from app.services.imports.customer_sales_import import _rebuild_customer_sales_product_candidates
    _rebuild_customer_sales_product_candidates(db, job)

    db.commit()

    return {
        "ok": True,
        "job_id": int(job_id),
        "total_rows": len(rows),
        "product_updated": product_updated,
        "store_updated": store_updated,
    }
