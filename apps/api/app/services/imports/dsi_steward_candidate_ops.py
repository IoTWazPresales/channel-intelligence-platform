"""Shared DSI import candidate steward operations for single-row routes and bulk workflows."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.ingestion import ImportJob
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.models.mapping import ProductAlias
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_product_steward import raw_product_token_for_dsi_candidate, validate_dsi_product_resolve

# Normalized distributor tokens that look like placeholders (single-row + bulk use the same rule).
DISTRIBUTOR_PROVISIONAL_SUSPICIOUS = frozenset(
    {
        "open channel",
        "open_channel",
        "cash sale",
        "internal",
        "n/a",
        "na",
        "tbd",
        "unknown",
        "misc",
        "blank",
        "",
    }
)


class StewardOpError(Exception):
    """Validation / conflict failure surfaced as HTTP error by routes."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


_DSI_STEWARD_TERMINAL_STATUSES = frozenset({"resolved", "ignored", "waived_open_channel"})


def _is_dsi_steward_terminal_status(status: str | None) -> bool:
    return (status or "").strip() in _DSI_STEWARD_TERMINAL_STATUSES


def _merge_duplicate_review_context(cand: ImportEntityMappingCandidate, review: dict[str, Any]) -> None:
    ctx = dict(cand.context) if isinstance(cand.context, dict) else {}
    ctx["duplicate_review"] = review
    cand.context = ctx


def _first_sample_raw(candidate: ImportEntityMappingCandidate) -> str:
    samples = candidate.sample_raw_values or []
    for s in samples:
        if isinstance(s, str) and s.strip():
            return s.strip()[:512]
    if candidate.normalized_key and candidate.normalized_key != "__blank__":
        return candidate.normalized_key[:512]
    return ""


def default_display_name_provisional_customer(cand: ImportEntityMappingCandidate) -> str:
    """Account label for new dim_customer — mirrors single-row steward default (Dealer Name Group path)."""
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("dealer_group_account_raw")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:256]
    if cand.dealer_group_token and str(cand.dealer_group_token).strip():
        return str(cand.dealer_group_token).strip()[:256]
    if cand.normalized_key and str(cand.normalized_key).strip() and cand.normalized_key != "__blank__":
        return str(cand.normalized_key).strip()[:256]
    fs = _first_sample_raw(cand)
    return (fs[:256] if fs else "Unknown customer")[:256]


def default_display_name_provisional_distributor(cand: ImportEntityMappingCandidate) -> str:
    """Display name for provisional distributor — same default as steward panel (token / sample)."""
    fs = _first_sample_raw(cand)
    if fs.strip():
        return fs.strip()[:256]
    if cand.normalized_key and cand.normalized_key != "__blank__":
        return str(cand.normalized_key).strip()[:256]
    return "Unknown distributor"


def _resolved_provisional_distributor_display_name(
    display_name_override: str | None, cand: ImportEntityMappingCandidate
) -> str:
    d = (display_name_override or "").strip()
    return d if d else default_display_name_provisional_distributor(cand)


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
    if _is_dsi_steward_terminal_status(cand.status):
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
    if _is_dsi_steward_terminal_status(cand.status):
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


async def _apply_map_dsi_customer_without_commit(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    """Map candidate to customer in the current session; caller must commit."""
    pv = await preview_map_dsi_customer(db, cand, customer_id=customer_id, raw_token=raw_token)
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)
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
    await db.flush()
    cand.status = "resolved"
    cand.suggested_entity_id = customer_id
    cand.match_reason = "steward_map_existing_customer"
    return {"ok": True, "alias_id": alias.id, "customer_id": customer_id, "candidate_id": cand.id}


async def execute_map_dsi_customer(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    customer_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    out = await _apply_map_dsi_customer_without_commit(
        db, cand, customer_id=customer_id, raw_token=raw_token
    )
    try:
        await db.commit()
        await db.refresh(cand)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError("Could not create alias (duplicate or invalid reference)", status_code=409) from None
    return out


async def preview_map_dsi_distributor(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "distributor_token":
        return {"ok": False, "skip_reason": "wrong_entity_type", "detail": "Not distributor_token"}
    if _is_dsi_steward_terminal_status(cand.status):
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
    if _is_dsi_steward_terminal_status(cand.status):
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


def _resolved_provisional_display_name(display_name_override: str | None, cand: ImportEntityMappingCandidate) -> str:
    d = (display_name_override or "").strip()
    return d if d else default_display_name_provisional_customer(cand)


async def generate_tmp_customer_code(db: AsyncSession) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _ in range(8):
        code_candidate = f"TMP-CUST-{stamp}-{secrets.token_hex(2).upper()}"
        exists = await db.execute(select(DimCustomer.id).where(DimCustomer.code == code_candidate))
        if exists.scalar_one_or_none() is None:
            return code_candidate
    raise StewardOpError(
        "Unable to generate a temporary customer code; retry.",
        status_code=503,
    )


async def generate_tmp_distributor_code(db: AsyncSession) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    for _ in range(8):
        code_candidate = f"TMP-DIST-{stamp}-{secrets.token_hex(2).upper()}"
        exists = await db.execute(select(DimDistributor.id).where(DimDistributor.code == code_candidate))
        if exists.scalar_one_or_none() is None:
            return code_candidate
    raise StewardOpError(
        "Unable to generate a temporary distributor code; retry.",
        status_code=503,
    )


async def preview_create_provisional_dsi_customer(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    display_name_override: str | None,
    region_id: int | None,
    channel_id: int | None,
    preferred_distributor_id: int | None,
    partner_tier: str | None,
    notes_summary: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        return {"ok": False, "skip_reason": "wrong_entity_type", "detail": "Not customer_dealer_token"}

    if cand.status == "resolved" and cand.match_reason == "steward_created_provisional_customer" and cand.suggested_entity_id:
        cust = await db.get(DimCustomer, int(cand.suggested_entity_id))
        if cust:
            ar = (
                await db.execute(
                    select(CustomerSourceTokenAlias).where(
                        CustomerSourceTokenAlias.import_entity_mapping_candidate_id == cand.id
                    )
                )
            ).scalars().first()
            return {
                "ok": True,
                "idempotent_noop": True,
                "detail": "Already resolved with provisional customer",
                "proposed_display_name": cust.name[:256],
                "customer_id": cust.id,
                "customer_code": cust.code,
                "source_customer_alias_raw_preview": ((ar.raw_token if ar else "")[:160]),
                "source_customer_alias_evidence": _source_customer_alias_raw_for_dsi_candidate(cand)[:512],
                "dealer_group_token": cand.dealer_group_token,
                "partner_tier": (cust.partner_tier or "")[:32],
                "region_id": cust.region_id,
                "channel_id": cust.channel_id,
            }

    if _is_dsi_steward_terminal_status(cand.status):
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}

    region: DimRegion | None = None
    channel: DimChannel | None = None
    if region_id is not None:
        region = await db.get(DimRegion, region_id)
        if not region:
            return {"ok": False, "skip_reason": "invalid_region", "detail": "Invalid region_id"}
    if channel_id is not None:
        channel = await db.get(DimChannel, channel_id)
        if not channel:
            return {"ok": False, "skip_reason": "invalid_channel", "detail": "Invalid channel_id"}
    if preferred_distributor_id is not None:
        pref = await db.get(DimDistributor, preferred_distributor_id)
        if not pref:
            return {"ok": False, "skip_reason": "invalid_preferred_distributor", "detail": "Invalid preferred_distributor_id"}

    tier = (partner_tier or "unmanaged").strip().lower()
    if tier not in {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail", "unmanaged"}:
        return {"ok": False, "skip_reason": "invalid_tier", "detail": "Invalid partner_tier"}

    proposal = _resolved_provisional_display_name(display_name_override, cand)
    raw_evidence = _source_customer_alias_raw_for_dsi_candidate(cand)
    if not raw_evidence.strip():
        return {"ok": False, "skip_reason": "missing_alias_evidence", "detail": "Candidate has no usable source customer alias evidence"}

    return {
        "ok": True,
        "detail": "Would create unverified dim_customer and CustomerSourceTokenAlias",
        "proposed_display_name": proposal[:256],
        "source_customer_alias_raw_preview": raw_evidence[:160],
        "source_customer_alias_evidence": raw_evidence[:512],
        "dealer_group_token": cand.dealer_group_token,
        "region_id": region_id,
        "region_code": (region.code or "")[:64] if region else None,
        "channel_id": channel_id,
        "channel_code": (channel.code or "")[:64] if channel else None,
        "preferred_distributor_id": preferred_distributor_id,
        "partner_tier": tier,
        "notes_summary_preview": ((notes_summary or "").strip()[:512]) if notes_summary else None,
    }


async def execute_create_provisional_dsi_customer(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    display_name_override: str | None,
    region_id: int | None,
    channel_id: int | None,
    preferred_distributor_id: int | None,
    partner_tier: str | None,
    notes_summary: str | None,
) -> dict[str, Any]:
    if cand.status == "resolved" and cand.match_reason == "steward_created_provisional_customer" and cand.suggested_entity_id:
        cust = await db.get(DimCustomer, int(cand.suggested_entity_id))
        if cust:
            alias_row = (
                await db.execute(
                    select(CustomerSourceTokenAlias).where(
                        CustomerSourceTokenAlias.import_entity_mapping_candidate_id == cand.id
                    )
                )
            ).scalars().first()
            return {
                "ok": True,
                "idempotent": True,
                "candidate_id": cand.id,
                "customer_id": cust.id,
                "customer_code": cust.code,
                "alias_id": int(alias_row.id) if alias_row else None,
            }

    pv = await preview_create_provisional_dsi_customer(
        db,
        cand,
        display_name_override=display_name_override,
        region_id=region_id,
        channel_id=channel_id,
        preferred_distributor_id=preferred_distributor_id,
        partner_tier=partner_tier,
        notes_summary=notes_summary,
    )
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)

    if region_id is not None:
        region = await db.get(DimRegion, region_id)
        if not region:
            raise StewardOpError("Invalid region_id", status_code=400)
    if channel_id is not None:
        channel = await db.get(DimChannel, channel_id)
        if not channel:
            raise StewardOpError("Invalid channel_id", status_code=400)
    if preferred_distributor_id is not None:
        pref = await db.get(DimDistributor, preferred_distributor_id)
        if not pref:
            raise StewardOpError("Invalid preferred_distributor_id", status_code=400)

    tier = (partner_tier or "unmanaged").strip().lower()
    proposal = _resolved_provisional_display_name(display_name_override, cand)
    notes = (notes_summary or "").strip() or None
    base_note = f"Provisional customer created from DSI import candidate {cand.id} (job {cand.import_job_id})."
    merged_notes = f"{base_note} {notes}" if notes else base_note

    code = await generate_tmp_customer_code(db)
    row = DimCustomer(
        code=code,
        name=proposal.strip()[:256],
        customer_status="unverified",
        partner_tier=tier,
        notes_summary=merged_notes[:512],
        region_id=region_id,
        channel_id=channel_id,
        preferred_distributor_id=preferred_distributor_id,
    )
    db.add(row)
    await db.flush()
    raw = _source_customer_alias_raw_for_dsi_candidate(cand)
    nt = _norm_key(raw)
    alias = CustomerSourceTokenAlias(
        customer_id=row.id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        distributor_id=None,
        dealer_group_token=cand.dealer_group_token,
        status="approved",
        notes=f"Alias from provisional customer create (candidate {cand.id})",
        created_from_import_job_id=cand.import_job_id,
        import_entity_mapping_candidate_id=cand.id,
    )
    db.add(alias)
    try:
        cand.status = "resolved"
        cand.suggested_entity_id = row.id
        cand.match_reason = "steward_created_provisional_customer"
        await db.commit()
        await db.refresh(row)
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError("Could not create customer or alias", status_code=409) from None

    return {
        "ok": True,
        "customer_id": row.id,
        "customer_code": row.code,
        "alias_id": alias.id,
        "candidate_id": cand.id,
    }


async def preview_create_provisional_dsi_distributor(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    display_name_override: str | None,
    distributor_code_override: str | None,
    confirm_for_suspicious_token: bool,
) -> dict[str, Any]:
    if cand.entity_type != "distributor_token":
        return {"ok": False, "skip_reason": "wrong_entity_type", "detail": "Not distributor_token"}

    if cand.status == "resolved" and cand.match_reason == "steward_created_provisional_distributor" and cand.suggested_entity_id:
        dist = await db.get(DimDistributor, int(cand.suggested_entity_id))
        if dist:
            ar = (
                await db.execute(
                    select(DistributorSourceTokenAlias)
                    .where(
                        DistributorSourceTokenAlias.distributor_id == dist.id,
                        DistributorSourceTokenAlias.created_from_import_job_id == cand.import_job_id,
                    )
                    .order_by(DistributorSourceTokenAlias.id)
                )
            ).scalars().first()
            # Fallback: any alias for this job tied to candidate via notes is brittle; prefer distributor match.
            return {
                "ok": True,
                "idempotent_noop": True,
                "detail": "Already resolved with provisional distributor",
                "proposed_display_name": dist.name[:256],
                "distributor_id": dist.id,
                "distributor_code": dist.code,
                "alias_raw_preview": ((ar.raw_token if ar else "")[:160]),
            }

    if _is_dsi_steward_terminal_status(cand.status):
        return {"ok": False, "skip_reason": "terminal_status", "detail": "Candidate already terminal"}

    nt_check = _norm_key(_first_sample_raw(cand) or cand.normalized_key or "")
    suspicious = nt_check in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
    if suspicious and not confirm_for_suspicious_token:
        return {
            "ok": False,
            "skip_reason": "suspicious_token_requires_confirm",
            "detail": "Token looks like a placeholder or internal label; confirm_for_suspicious_token=true to create",
            "suspicious_token": True,
            "proposed_display_name": _resolved_provisional_distributor_display_name(display_name_override, cand),
        }

    raw = _first_sample_raw(cand)
    if not raw.strip():
        return {"ok": False, "skip_reason": "missing_token", "detail": "Candidate has no usable raw token sample"}

    proposal = _resolved_provisional_distributor_display_name(display_name_override, cand)
    code_preview = (distributor_code_override or "").strip()[:32] or "(auto-generated TMP-DIST-…)"

    return {
        "ok": True,
        "detail": "Would create dim_distributor and DistributorSourceTokenAlias",
        "proposed_display_name": proposal[:256],
        "distributor_code_preview": code_preview,
        "alias_raw_preview": raw[:160],
        "normalized_token_preview": _norm_key(raw)[:512],
        "suspicious_token": suspicious,
    }


async def execute_create_provisional_dsi_distributor(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    display_name_override: str | None,
    distributor_code_override: str | None,
    confirm_for_suspicious_token: bool,
) -> dict[str, Any]:
    if cand.status == "resolved" and cand.match_reason == "steward_created_provisional_distributor" and cand.suggested_entity_id:
        dist = await db.get(DimDistributor, int(cand.suggested_entity_id))
        if dist:
            alias_row = (
                await db.execute(
                    select(DistributorSourceTokenAlias)
                    .where(
                        DistributorSourceTokenAlias.distributor_id == dist.id,
                        DistributorSourceTokenAlias.created_from_import_job_id == cand.import_job_id,
                    )
                    .order_by(DistributorSourceTokenAlias.id)
                )
            ).scalars().first()
            return {
                "ok": True,
                "idempotent": True,
                "candidate_id": cand.id,
                "distributor_id": dist.id,
                "distributor_code": dist.code,
                "alias_id": int(alias_row.id) if alias_row else None,
            }

    pv = await preview_create_provisional_dsi_distributor(
        db,
        cand,
        display_name_override=display_name_override,
        distributor_code_override=distributor_code_override,
        confirm_for_suspicious_token=confirm_for_suspicious_token,
    )
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)

    nt_check = _norm_key(_first_sample_raw(cand) or cand.normalized_key or "")
    if nt_check in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS and not confirm_for_suspicious_token:
        raise StewardOpError(
            "Token looks like a placeholder or internal label; set confirm_for_suspicious_token=true to create a provisional distributor anyway.",
            status_code=400,
        )

    code = (distributor_code_override or "").strip() or await generate_tmp_distributor_code(db)
    existing = await db.execute(select(DimDistributor.id).where(DimDistributor.code == code))
    if existing.scalar_one_or_none() is not None:
        raise StewardOpError(
            "distributor_code already exists; omit distributor_code to auto-generate",
            status_code=409,
        )

    proposal = _resolved_provisional_distributor_display_name(display_name_override, cand)
    row = DimDistributor(code=code[:32], name=proposal.strip()[:256])
    db.add(row)
    await db.flush()
    raw = _first_sample_raw(cand)
    nt = _norm_key(raw)
    alias = DistributorSourceTokenAlias(
        distributor_id=row.id,
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Provisional distributor from candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        cand.status = "resolved"
        cand.suggested_entity_id = row.id
        cand.match_reason = "steward_created_provisional_distributor"
        await db.commit()
        await db.refresh(row)
        await db.refresh(alias)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError("Could not create distributor or alias", status_code=409) from None

    return {
        "ok": True,
        "distributor_id": row.id,
        "distributor_code": row.code,
        "alias_id": alias.id,
        "candidate_id": cand.id,
    }


async def _get_dsi_customer_peer_candidate(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    peer_normalized_key: str,
) -> ImportEntityMappingCandidate | None:
    nk = (peer_normalized_key or "").strip()[:512]
    if not nk:
        return None
    return await db.scalar(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == cand.import_job_id,
            ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            ImportEntityMappingCandidate.normalized_key == nk,
        )
    )


async def execute_acknowledge_dsi_duplicate_different_entity(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    peer_normalized_key: str,
    audit_note: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        raise StewardOpError("Not customer_dealer_token", status_code=400)
    if _is_dsi_steward_terminal_status(cand.status):
        raise StewardOpError("Candidate already terminal", status_code=400)
    from app.services.imports.dsi_customer_intelligence import (
        build_duplicate_review_record,
        dsi_candidate_duplicate_review_unresolved,
        similarity_score_for_duplicate_peer,
    )

    if not dsi_candidate_duplicate_review_unresolved(cand):
        raise StewardOpError("Duplicate review already recorded for this candidate", status_code=400)
    peer = await _get_dsi_customer_peer_candidate(db, cand, peer_normalized_key)
    if peer is None:
        raise StewardOpError("Peer candidate not found for this import job", status_code=404)
    ctx = cand.context if isinstance(cand.context, dict) else {}
    score = similarity_score_for_duplicate_peer(ctx, peer_normalized_key)
    review = build_duplicate_review_record(
        decision="different_entity",
        paired_normalized_key=peer.normalized_key,
        similarity_score=score,
        audit_note=audit_note,
        hints_snapshot=ctx.get("possible_duplicate_of") if isinstance(ctx.get("possible_duplicate_of"), list) else [],
    )
    _merge_duplicate_review_context(cand, review)
    cand.status = "acknowledged_unique"
    cand.match_reason = "steward_acknowledged_unique_duplicate"
    await db.commit()
    await db.refresh(cand)
    return {
        "ok": True,
        "candidate_id": cand.id,
        "status": cand.status,
        "peer_candidate_id": peer.id,
        "duplicate_review": review,
    }


def _optional_suggested_entity_id(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return None
    return iv if iv >= 1 else None


def resolve_duplicate_same_entity_customer_id(
    *,
    customer_id: int | None,
    primary_suggested_entity_id: int | None,
    peer_suggested_entity_id: int | None,
) -> tuple[int, bool]:
    """
    Resolve target dim_customer for same-entity duplicate review.

    Returns (customer_id, needs_provisional_create).
    Raises StewardOpError 409 when both suggestions differ.
    """
    explicit = _optional_suggested_entity_id(customer_id)
    if explicit is not None:
        return explicit, False

    primary_sug = _optional_suggested_entity_id(primary_suggested_entity_id)
    peer_sug = _optional_suggested_entity_id(peer_suggested_entity_id)

    if primary_sug is not None and peer_sug is not None and primary_sug != peer_sug:
        raise StewardOpError(
            "Conflicting customer suggestions on primary and peer candidates — resolve each separately.",
            status_code=409,
        )
    if primary_sug is not None:
        return primary_sug, False
    if peer_sug is not None:
        return peer_sug, False
    return 0, True


async def _derive_provisional_geo_for_same_entity(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
) -> tuple[int | None, int | None]:
    from app.services.imports.dsi_resolution_plan import derive_effective_provisional_customer_geo_sync

    def _geo(sess: Any) -> dict[str, Any]:
        jid = cand.import_job_id
        job = sess.get(ImportJob, int(jid)) if jid is not None else None
        return derive_effective_provisional_customer_geo_sync(
            sess,
            cand,
            default_region_id=None,
            default_channel_id=None,
            import_job=job,
        )

    g = await db.run_sync(_geo)
    if bool(g.get("provisional_region_conflict")):
        raise StewardOpError(
            str(g.get("source_region_resolution_message") or "Conflicting region evidence on primary token."),
            status_code=400,
        )
    if bool(g.get("provisional_channel_conflict")):
        raise StewardOpError(
            str(g.get("source_channel_resolution_message") or "Conflicting channel evidence on primary token."),
            status_code=400,
        )
    er = g.get("effective_region_id")
    ec = g.get("effective_channel_id")
    region_id = int(er) if er is not None else None
    channel_id = int(ec) if ec is not None else None
    return region_id, channel_id


async def _create_provisional_dim_customer_for_same_entity(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
) -> int:
    """Create unverified dim_customer from primary token evidence; does not resolve the candidate."""
    pv = await preview_create_provisional_dsi_customer(
        db,
        cand,
        display_name_override=None,
        region_id=None,
        channel_id=None,
        preferred_distributor_id=None,
        partner_tier=None,
        notes_summary=None,
    )
    if not pv.get("ok"):
        raise StewardOpError(pv.get("detail") or "preview failed", status_code=400)

    region_id, channel_id = await _derive_provisional_geo_for_same_entity(db, cand)
    tier = "unmanaged"
    proposal = _resolved_provisional_display_name(None, cand)
    base_note = (
        f"Provisional customer created for same-entity duplicate review "
        f"(candidate {cand.id}, job {cand.import_job_id})."
    )
    code = await generate_tmp_customer_code(db)
    row = DimCustomer(
        code=code,
        name=proposal.strip()[:256],
        customer_status="unverified",
        partner_tier=tier,
        notes_summary=base_note[:512],
        region_id=region_id,
        channel_id=channel_id,
        preferred_distributor_id=None,
    )
    db.add(row)
    await db.flush()
    return int(row.id)


async def execute_dsi_duplicate_same_entity(
    db: AsyncSession,
    cand: ImportEntityMappingCandidate,
    *,
    peer_normalized_key: str,
    customer_id: int | None,
    raw_token: str | None,
    audit_note: str | None,
) -> dict[str, Any]:
    if cand.entity_type != "customer_dealer_token":
        raise StewardOpError("Not customer_dealer_token", status_code=400)
    if _is_dsi_steward_terminal_status(cand.status):
        raise StewardOpError("Candidate already terminal", status_code=400)
    from app.services.imports.dsi_customer_intelligence import (
        build_duplicate_review_record,
        dsi_candidate_duplicate_review_unresolved,
        duplicate_review_decision,
        similarity_score_for_duplicate_peer,
    )

    if duplicate_review_decision(cand.context if isinstance(cand.context, dict) else {}):
        raise StewardOpError("Duplicate review already recorded for this candidate", status_code=400)
    if not dsi_candidate_duplicate_review_unresolved(cand):
        raise StewardOpError("No unresolved duplicate hints on this candidate", status_code=400)
    peer = await _get_dsi_customer_peer_candidate(db, cand, peer_normalized_key)
    if peer is None:
        raise StewardOpError("Peer candidate not found for this import job", status_code=404)
    if peer.id == cand.id:
        raise StewardOpError(
            "peer_normalized_key must differ from this candidate",
            status_code=400,
        )

    target_id, needs_provisional = resolve_duplicate_same_entity_customer_id(
        customer_id=customer_id,
        primary_suggested_entity_id=cand.suggested_entity_id,
        peer_suggested_entity_id=peer.suggested_entity_id,
    )
    created_provisional: dict[str, Any] | None = None

    try:
        if needs_provisional:
            new_cid = await _create_provisional_dim_customer_for_same_entity(db, cand)
            target_id = new_cid
            created_provisional = {"customer_id": new_cid}

        primary_out = await _apply_map_dsi_customer_without_commit(
            db, cand, customer_id=target_id, raw_token=raw_token
        )
        peer_out: dict[str, Any] | None = None
        if not _is_dsi_steward_terminal_status(peer.status):
            peer_out = await _apply_map_dsi_customer_without_commit(
                db, peer, customer_id=target_id, raw_token=None
            )

        ctx_p = cand.context if isinstance(cand.context, dict) else {}
        peer_nk = (peer.normalized_key or "").strip()
        primary_nk = (cand.normalized_key or "").strip()
        score = similarity_score_for_duplicate_peer(ctx_p, peer_nk)
        hints = ctx_p.get("possible_duplicate_of") if isinstance(ctx_p.get("possible_duplicate_of"), list) else []
        review_primary = build_duplicate_review_record(
            decision="same_entity",
            paired_normalized_key=peer_nk,
            similarity_score=score,
            customer_id=target_id,
            audit_note=audit_note,
            hints_snapshot=hints,
        )
        peer_ctx = peer.context if isinstance(peer.context, dict) else {}
        review_peer = build_duplicate_review_record(
            decision="same_entity",
            paired_normalized_key=primary_nk,
            similarity_score=score,
            customer_id=target_id,
            audit_note=audit_note,
            hints_snapshot=peer_ctx.get("possible_duplicate_of")
            if isinstance(peer_ctx.get("possible_duplicate_of"), list)
            else [],
        )
        _merge_duplicate_review_context(cand, review_primary)
        _merge_duplicate_review_context(peer, review_peer)
        await db.commit()
        await db.refresh(cand)
        await db.refresh(peer)
    except IntegrityError:
        await db.rollback()
        raise StewardOpError("Could not complete same-entity mapping (duplicate or invalid reference)", status_code=409) from None
    except Exception:
        await db.rollback()
        raise

    return {
        "ok": True,
        "candidate_id": cand.id,
        "peer_candidate_id": peer.id,
        "customer_id": target_id,
        "created_provisional": created_provisional,
        "primary_map": primary_out,
        "peer_map": peer_out,
        "duplicate_review": review_primary,
    }

