"""Shared DSI import candidate steward operations for single-row routes and bulk workflows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.models.mapping import ProductAlias
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_product_steward import raw_product_token_for_dsi_candidate, validate_dsi_product_resolve


class StewardOpError(Exception):
    """Validation / conflict failure surfaced as HTTP error by routes."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _first_sample_raw(candidate: ImportEntityMappingCandidate) -> str:
    samples = candidate.sample_raw_values or []
    for s in samples:
        if isinstance(s, str) and s.strip():
            return s.strip()[:512]
    if candidate.normalized_key and candidate.normalized_key != "__blank__":
        return candidate.normalized_key[:512]
    return ""


def _source_customer_alias_raw_for_dsi_candidate(candidate: ImportEntityMappingCandidate) -> str:
    ctx = candidate.context if isinstance(candidate.context, dict) else {}
    samples = ctx.get("source_customer_name_raw_samples")
    if isinstance(samples, list):
        for s in samples:
            if isinstance(s, str) and s.strip():
                return s.strip()[:512]
    return _first_sample_raw(candidate)


async def preview_resolve_dsi_product(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    product_id: int,
    raw_token: str | None,
    confirm_ineligible_product: bool,
    audit_note: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "product_identifier":
        return {
            "ok": False,
            "skip_reason": "wrong_entity_type",
            "detail": "Candidate is not product_identifier",
        }
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        return {
            "ok": False,
            "skip_reason": "terminal_status",
            "detail": "Candidate already terminal",
        }
    prod = await db.get(DimProduct, product_id)
    if not prod:
        return {"ok": False, "skip_reason": "product_not_found", "detail": "product_id not found"}
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = raw_product_token_for_dsi_candidate(
        sample_raw_values=cand.sample_raw_values if isinstance(cand.sample_raw_values, list) else None,
        normalized_key=cand.normalized_key or "",
        raw_override=raw_token,
    )
    if not raw.strip():
        return {"ok": False, "skip_reason": "missing_token", "detail": "Could not determine raw product token"}
    nt = _norm_key(raw)
    if not nt:
        return {"ok": False, "skip_reason": "empty_norm", "detail": "Token empty after normalization"}
    raw_val = raw.strip()[:256]
    try:
        validate_dsi_product_resolve(
            context=ctx,
            selected_product_id=product_id,
            selected_product=prod,
            confirm_ineligible_product=confirm_ineligible_product,
            audit_note=audit_note,
        )
    except ValueError as exc:
        return {"ok": False, "skip_reason": "validation", "detail": str(exc)}
    existing = (
        await db.execute(select(ProductAlias).where(func.lower(ProductAlias.alias_value) == raw_val.lower()))
    ).scalars().first()
    would_create_alias = existing is None
    conflict = False
    if existing is not None and int(existing.product_id) != int(product_id):
        conflict = True
    return {
        "ok": not conflict,
        "skip_reason": "alias_conflict" if conflict else None,
        "detail": (
            "Token already aliased to a different product"
            if conflict
            else "Would approve ProductAlias for this token"
        ),
        "would_create_product_alias": would_create_alias,
        "raw_token_used": raw_val,
        "normalized_token": nt[:512],
        "product_id": int(product_id),
        "sku": (prod.sku or "")[:128],
    }


async def execute_resolve_dsi_product(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    product_id: int,
    raw_token: str | None,
    confirm_ineligible_product: bool,
    audit_note: str | None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    pv = await preview_resolve_dsi_product(
        db,
        cand,
        product_id=product_id,
        raw_token=raw_token,
        confirm_ineligible_product=confirm_ineligible_product,
        audit_note=audit_note,
    )
    if not pv.get("ok"):
        sr = pv.get("skip_reason")
        code = 409 if sr == "alias_conflict" else 400
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=code)
    prod = await db.get(DimProduct, product_id)
    assert prod is not None
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = raw_product_token_for_dsi_candidate(
        sample_raw_values=cand.sample_raw_values if isinstance(cand.sample_raw_values, list) else None,
        normalized_key=cand.normalized_key or "",
        raw_override=raw_token,
    )
    raw_val = raw.strip()[:256]
    nt = _norm_key(raw)
    existing = (
        await db.execute(select(ProductAlias).where(func.lower(ProductAlias.alias_value) == raw_val.lower()))
    ).scalars().first()
    alias_row: ProductAlias
    if existing is not None:
        if int(existing.product_id) != int(product_id):
            raise StewardOpError(
                "This source token is already aliased to a different product; resolve the conflict in Product Master first.",
                status_code=409,
            )
        alias_row = existing
    else:
        alias_row = ProductAlias(
            product_id=int(product_id),
            alias_value=raw_val,
            alias_kind="source_import_token",
            confidence="steward_approved",
        )
        db.add(alias_row)
    try:
        await db.flush()
        cand.status = "resolved"
        cand.suggested_entity_id = int(product_id)
        cand.match_reason = "steward_resolve_product_alias"
        ctx2 = dict(ctx)
        ctx2["steward_product_resolution"] = {
            "product_id": int(product_id),
            "product_alias_id": int(alias_row.id),
            "raw_token_used": raw_val,
            "normalized_token": nt[:512],
            "import_job_id": int(cand.import_job_id),
            "import_entity_mapping_candidate_id": int(cand.id),
            "confirm_ineligible_product": bool(confirm_ineligible_product),
            "audit_note": (audit_note or "").strip()[:2000] if confirm_ineligible_product else None,
            "idempotency_key": (idempotency_key or "").strip()[:128] or None,
        }
        cand.context = ctx2
        await db.commit()
        await db.refresh(alias_row)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError(
            "Could not create product alias (duplicate or constraint violation)",
            status_code=409,
        ) from None
    return {
        "ok": True,
        "candidate_id": cand.id,
        "product_id": int(product_id),
        "product_alias_id": int(alias_row.id),
    }


async def preview_map_dsi_customer(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        return {"ok": False, "skip_reason": "wrong_entity_type", "detail": "Not customer_dealer_token"}
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}
    cust = await db.get(DimCustomer, customer_id)
    if not cust:
        return {"ok": False, "skip_reason": "customer_not_found", "detail": "customer_id not found"}
    raw = (raw_token or _source_customer_alias_raw_for_dsi_candidate(cand)).strip()
    if not raw:
        return {"ok": False, "skip_reason": "missing_token", "detail": "raw_token required"}
    nt = _norm_key(raw)
    if not nt:
        return {"ok": False, "skip_reason": "empty_norm", "detail": "raw_token empty after normalization"}
    return {
        "ok": True,
        "detail": "Would create CustomerSourceTokenAlias",
        "customer_id": customer_id,
        "customer_code": cust.code,
        "customer_name": cust.name,
        "alias_raw_preview": raw[:160],
    }


async def execute_map_dsi_customer(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    pv = await preview_map_dsi_customer(db, cand, customer_id=customer_id, raw_token=raw_token)
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)
    cust = await db.get(DimCustomer, customer_id)
    assert cust is not None
    raw = (raw_token or _source_customer_alias_raw_for_dsi_candidate(cand)).strip()
    nt = _norm_key(raw)
    alias = CustomerSourceTokenAlias(
        customer_id=customer_id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        status="approved",
        notes=f"Mapped from import candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    db.add(alias)
    try:
        cand.status = "resolved"
        cand.suggested_entity_id = customer_id
        cand.match_reason = "steward_map_existing_customer"
        await db.commit()
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError("Could not create alias (duplicate or invalid reference)", status_code=409) from None
    return {"ok": True, "alias_id": alias.id, "customer_id": customer_id, "candidate_id": cand.id}


async def preview_map_dsi_distributor(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "distributor_token":
        return {"ok": False, "skip_reason": "wrong_entity_type", "detail": "Not distributor_token"}
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}
    dist = await db.get(DimDistributor, distributor_id)
    if not dist:
        return {"ok": False, "skip_reason": "distributor_not_found", "detail": "distributor_id not found"}
    raw = (raw_token or _first_sample_raw(cand)).strip()
    if not raw:
        return {"ok": False, "skip_reason": "missing_token", "detail": "raw_token required"}
    nt = _norm_key(raw)
    if not nt:
        return {"ok": False, "skip_reason": "empty_norm", "detail": "raw_token empty after normalization"}
    return {
        "ok": True,
        "detail": "Would create DistributorSourceTokenAlias",
        "distributor_id": distributor_id,
        "distributor_code": dist.code,
        "alias_raw_preview": raw[:160],
    }


async def execute_map_dsi_distributor(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    pv = await preview_map_dsi_distributor(db, cand, distributor_id=distributor_id, raw_token=raw_token)
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)
    raw = (raw_token or _first_sample_raw(cand)).strip()
    nt = _norm_key(raw)
    alias = DistributorSourceTokenAlias(
        distributor_id=distributor_id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Mapped from import candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        cand.status = "resolved"
        cand.suggested_entity_id = distributor_id
        cand.match_reason = "steward_map_existing_distributor"
        await db.commit()
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError("Could not create distributor alias", status_code=409) from None
    return {"ok": True, "alias_id": alias.id, "distributor_id": distributor_id, "candidate_id": cand.id}


async def preview_ignore_dsi_candidate(
    cand: ImportEntityMappingCandidate,
    *,
    notes: str | None,
) -> dict[str, Any]:
    if cand.entity_type not in {"customer_dealer_token", "distributor_token", "product_identifier"}:
        return {"ok": False, "skip_reason": "wrong_entity_type", "detail": "Unsupported entity_type for ignore"}
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}
    return {"ok": True, "detail": "Would set status ignored", "notes": notes}


async def execute_ignore_dsi_candidate(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    notes: str | None,
) -> dict[str, Any]:
    pv = await preview_ignore_dsi_candidate(cand, notes=notes)
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)
    cand.status = "ignored"
    if notes:
        ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
        ctx["steward_ignore_notes"] = notes[:2000]
        cand.context = ctx
    await db.commit()
    return {"ok": True, "candidate_id": cand.id, "status": cand.status}
