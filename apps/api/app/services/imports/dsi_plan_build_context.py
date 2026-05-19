"""Pre-loaded reference data for fast DSI resolution plan generation (one pass per request)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimRegion
from app.models.import_distributor_si import ChannelSourceTokenAlias, RegionSourceTokenAlias
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    ProductResolutionIndex,
    _build_resolution_cache,
    _load_product_resolution_index,
    _norm_key,
    _resolve_customer_from_cache,
    _resolve_distributor_from_cache,
)


@dataclass(frozen=True)
class DSIPlanBuildContext:
    """In-memory lookups shared across all ``plan_dsi_candidate_sync`` calls in one plan request."""

    res_cache: DSIResolutionCache
    prod_idx: ProductResolutionIndex
    regions_by_id: dict[int, DimRegion]
    channels_by_id: dict[int, DimChannel]
    region_code_lower: dict[str, int]
    region_name_lower: dict[str, int]
    channel_code_lower: dict[str, int]
    channel_name_lower: dict[str, int]
    region_aliases: tuple[RegionSourceTokenAlias, ...]
    channel_aliases: tuple[ChannelSourceTokenAlias, ...]


def build_dsi_plan_build_context(session: Session) -> DSIPlanBuildContext:
    res_cache = _build_resolution_cache(session, None)
    prod_idx = _load_product_resolution_index(session)

    regions = list(session.scalars(select(DimRegion)).all())
    channels = list(session.scalars(select(DimChannel)).all())
    regions_by_id = {int(r.id): r for r in regions}
    channels_by_id = {int(c.id): c for c in channels}

    region_code_lower: dict[str, int] = {}
    region_name_lower: dict[str, int] = {}
    for r in regions:
        ck = (r.code or "").strip().lower()
        if ck:
            region_code_lower[ck] = int(r.id)
        nk = (r.name or "").strip().lower()
        if nk:
            region_name_lower[nk] = int(r.id)

    channel_code_lower: dict[str, int] = {}
    channel_name_lower: dict[str, int] = {}
    for c in channels:
        ck = (c.code or "").strip().lower()
        if ck:
            channel_code_lower[ck] = int(c.id)
        nk = (c.name or "").strip().lower()
        if nk:
            channel_name_lower[nk] = int(c.id)

    region_aliases = tuple(
        session.scalars(select(RegionSourceTokenAlias).where(RegionSourceTokenAlias.status == "approved")).all()
    )
    channel_aliases = tuple(
        session.scalars(select(ChannelSourceTokenAlias).where(ChannelSourceTokenAlias.status == "approved")).all()
    )

    return DSIPlanBuildContext(
        res_cache=res_cache,
        prod_idx=prod_idx,
        regions_by_id=regions_by_id,
        channels_by_id=channels_by_id,
        region_code_lower=region_code_lower,
        region_name_lower=region_name_lower,
        channel_code_lower=channel_code_lower,
        channel_name_lower=channel_name_lower,
        region_aliases=region_aliases,
        channel_aliases=channel_aliases,
    )


def _alias_region_id_cached(
    ctx: DSIPlanBuildContext, source_id: int | None, normalized_token: str
) -> tuple[int | None, str | None]:
    nt = (normalized_token or "").strip()
    if not nt:
        return None, None
    matches: list[int] = []
    for a in ctx.region_aliases:
        if a.normalized_token != nt:
            continue
        if source_id is not None and a.source_definition_id is not None and a.source_definition_id != source_id:
            continue
        matches.append(int(a.region_id))
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0], "source_region_token_alias"
    if len(unique) > 1:
        return None, "conflicting_region_token_aliases"
    return None, None


def _alias_channel_id_cached(
    ctx: DSIPlanBuildContext, source_id: int | None, normalized_token: str
) -> tuple[int | None, str | None]:
    nt = (normalized_token or "").strip()
    if not nt:
        return None, None
    matches: list[int] = []
    for a in ctx.channel_aliases:
        if a.normalized_token != nt:
            continue
        if source_id is not None and a.source_definition_id is not None and a.source_definition_id != source_id:
            continue
        matches.append(int(a.channel_id))
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0], "source_channel_token_alias"
    if len(unique) > 1:
        return None, "conflicting_channel_token_aliases"
    return None, None


def _resolve_dim_region_from_source_cached(
    ctx: DSIPlanBuildContext, raw: str | None, *, source_definition_id: int | None = None
) -> tuple[int | None, str | None]:
    s = (raw or "").strip()
    if not s:
        return None, "blank"
    ck = s.lower()
    if ck in ctx.region_code_lower:
        return ctx.region_code_lower[ck], None
    nk = _norm_key(s)
    if nk in ctx.region_name_lower:
        return ctx.region_name_lower[nk], None
    rid, alias_reason = _alias_region_id_cached(ctx, source_definition_id, nk)
    if rid is not None:
        return rid, alias_reason or "source_region_token_alias"
    if alias_reason == "conflicting_region_token_aliases":
        return None, alias_reason
    return None, "no_catalog_match"


def _resolve_dim_channel_from_source_cached(
    ctx: DSIPlanBuildContext, raw: str | None, *, source_definition_id: int | None = None
) -> tuple[int | None, str | None]:
    s = (raw or "").strip()
    if not s:
        return None, "blank"
    ck = s.lower()
    if ck in ctx.channel_code_lower:
        return ctx.channel_code_lower[ck], "catalog_match"
    nk = _norm_key(s)
    if nk in ctx.channel_name_lower:
        return ctx.channel_name_lower[nk], "catalog_match"
    cid, alias_reason = _alias_channel_id_cached(ctx, source_definition_id, nk)
    if cid is not None:
        return cid, alias_reason or "source_channel_token_alias"
    if alias_reason == "conflicting_channel_token_aliases":
        return None, alias_reason
    return None, "no_catalog_match"


def _pick_raw_for_norm(samples: list[Any], norm: str) -> str | None:
    for item in samples:
        if isinstance(item, str) and _norm_key(item) == norm:
            return item.strip()
    return norm


def resolve_source_geo_from_ctx_cached(
    ctx: DSIPlanBuildContext,
    cand_ctx: dict[str, Any],
    *,
    source_definition_id: int | None = None,
) -> dict[str, Any]:
    reg_conflict = bool(cand_ctx.get("provisional_region_conflict"))
    ch_conflict = bool(cand_ctx.get("provisional_channel_conflict"))
    out: dict[str, Any] = {
        "source_region_resolved_id": None,
        "source_channel_resolved_id": None,
        "provisional_region_conflict": reg_conflict,
        "provisional_channel_conflict": ch_conflict,
        "source_region_resolution_detail": None,
        "source_channel_resolution_detail": None,
        "source_region_raw_token": None,
        "source_channel_raw_token": None,
    }
    reg_norms = [n for n in (cand_ctx.get("source_region_evidence_norms") or []) if isinstance(n, str) and n.strip()]
    ch_norms = [n for n in (cand_ctx.get("source_channel_evidence_norms") or []) if isinstance(n, str) and n.strip()]
    reg_samples = cand_ctx.get("source_region_raw_samples") or []
    ch_samples = cand_ctx.get("source_channel_raw_samples") or []

    if reg_conflict:
        out["source_region_resolution_detail"] = "conflicting_source_evidence"
    else:
        uniq_r = sorted(set(reg_norms))
        if len(uniq_r) == 1:
            raw_pick = _pick_raw_for_norm(reg_samples if isinstance(reg_samples, list) else [], uniq_r[0])
            if raw_pick:
                out["source_region_raw_token"] = str(raw_pick).strip()[:512]
            rid, reason = _resolve_dim_region_from_source_cached(ctx, raw_pick, source_definition_id=source_definition_id)
            out["source_region_resolved_id"] = rid
            out["source_region_resolution_detail"] = reason or ("catalog_match" if rid else "unresolved")
        elif len(uniq_r) == 0:
            out["source_region_resolution_detail"] = "missing_source_evidence"

    if ch_conflict:
        out["source_channel_resolution_detail"] = "conflicting_source_evidence"
    else:
        uniq_c = sorted(set(ch_norms))
        if len(uniq_c) == 1:
            raw_pick_c = _pick_raw_for_norm(ch_samples if isinstance(ch_samples, list) else [], uniq_c[0])
            if raw_pick_c:
                out["source_channel_raw_token"] = str(raw_pick_c).strip()[:512]
            cid, reason_c = _resolve_dim_channel_from_source_cached(
                ctx, raw_pick_c, source_definition_id=source_definition_id
            )
            out["source_channel_resolved_id"] = cid
            out["source_channel_resolution_detail"] = reason_c or ("catalog_match" if cid else "unresolved")
        elif len(uniq_c) == 0:
            out["source_channel_resolution_detail"] = "missing_source_evidence"

    return out


def dim_region_brief_cached(ctx: DSIPlanBuildContext, region_id: int | None) -> tuple[str | None, str | None]:
    if region_id is None:
        return None, None
    row = ctx.regions_by_id.get(int(region_id))
    if not row:
        return None, None
    return (row.code or "")[:64], (row.name or "")[:256]


def dim_channel_brief_cached(ctx: DSIPlanBuildContext, channel_id: int | None) -> tuple[str | None, str | None]:
    if channel_id is None:
        return None, None
    row = ctx.channels_by_id.get(int(channel_id))
    if not row:
        return None, None
    return (row.code or "")[:64], (row.name or "")[:256]


def resolve_distributor_for_plan(
    ctx: DSIPlanBuildContext, raw: str | None, source_id: int | None
) -> tuple[int | None, str | None]:
    return _resolve_distributor_from_cache(raw, source_id, ctx.res_cache)


def derive_effective_provisional_customer_geo_for_plan(
    plan_ctx: DSIPlanBuildContext,
    cand: ImportEntityMappingCandidate,
    *,
    default_region_id: int | None,
    default_channel_id: int | None,
    import_job: ImportJob | None = None,
) -> dict[str, Any]:
    """Cached geo derivation for resolution plan rows (no per-candidate catalog DB round-trips)."""
    from app.services.imports.dsi_resolution_plan import (
        _provisional_geo_dimension_message,
        dsi_geo_channel_alias_source_id,
    )

    cand_ctx = cand.context if isinstance(cand.context, dict) else {}
    src_def = dsi_geo_channel_alias_source_id(cand, import_job)
    geo = resolve_source_geo_from_ctx_cached(plan_ctx, cand_ctx, source_definition_id=src_def)
    src_r = geo.get("source_region_resolved_id")
    src_c = geo.get("source_channel_resolved_id")
    src_r = int(src_r) if src_r is not None else None
    src_c = int(src_c) if src_c is not None else None
    eff_r = src_r if src_r is not None else default_region_id
    eff_c = src_c if src_c is not None else default_channel_id
    rc, rn = dim_region_brief_cached(plan_ctx, src_r)
    cc, cn = dim_channel_brief_cached(plan_ctx, src_c)
    erc, ern = dim_region_brief_cached(plan_ctx, eff_r)
    ecc, ecn = dim_channel_brief_cached(plan_ctx, eff_c)

    reg_conflict = bool(geo.get("provisional_region_conflict"))
    ch_conflict = bool(geo.get("provisional_channel_conflict"))
    dr = geo.get("source_region_resolution_detail")
    dc = geo.get("source_channel_resolution_detail")
    raw_rt = geo.get("source_region_raw_token")
    raw_ct = geo.get("source_channel_raw_token")
    used_global_fallback_region = bool(
        not reg_conflict
        and src_r is None
        and default_region_id is not None
        and eff_r is not None
        and int(eff_r) == int(default_region_id)
    )
    used_global_fallback_channel = bool(
        not ch_conflict
        and src_c is None
        and default_channel_id is not None
        and eff_c is not None
        and int(eff_c) == int(default_channel_id)
    )

    if reg_conflict:
        source_region_resolution_message = _provisional_geo_dimension_message(
            detail="conflicting_source_evidence",
            raw_token=None,
            dim_short="region",
            dim_long="region / province",
        )
    elif src_r is not None:
        reg_detail = geo.get("source_region_resolution_detail")
        if reg_detail == "source_region_token_alias":
            source_region_resolution_message = (
                f"Approved source region token → catalog region: {rc or '?'}" + (f" — {rn}" if rn else "") + "."
            )
        else:
            source_region_resolution_message = (
                f"File → catalog region: {rc or '?'}" + (f" — {rn}" if rn else "") + "."
            )
    else:
        source_region_resolution_message = _provisional_geo_dimension_message(
            detail=dr if isinstance(dr, str) else None,
            raw_token=raw_rt if isinstance(raw_rt, str) else None,
            dim_short="region",
            dim_long="region / province",
        )

    if ch_conflict:
        source_channel_resolution_message = _provisional_geo_dimension_message(
            detail="conflicting_source_evidence",
            raw_token=None,
            dim_short="channel",
            dim_long="channel / route-to-market",
        )
    elif src_c is not None:
        ch_detail = geo.get("source_channel_resolution_detail")
        if ch_detail == "source_channel_token_alias":
            source_channel_resolution_message = (
                f"Approved source channel token → catalog channel: {cc or '?'}" + (f" — {cn}" if cn else "") + "."
            )
        else:
            source_channel_resolution_message = (
                f"File → catalog channel: {cc or '?'}" + (f" — {cn}" if cn else "") + "."
            )
    else:
        source_channel_resolution_message = _provisional_geo_dimension_message(
            detail=dc if isinstance(dc, str) else None,
            raw_token=raw_ct if isinstance(raw_ct, str) else None,
            dim_short="channel",
            dim_long="channel / route-to-market",
        )

    return {
        **geo,
        "suggested_region_id": src_r,
        "suggested_channel_id": src_c,
        "effective_region_id": eff_r,
        "effective_channel_id": eff_c,
        "suggested_region_code": rc,
        "suggested_region_name": rn,
        "suggested_channel_code": cc,
        "suggested_channel_name": cn,
        "effective_region_code": erc,
        "effective_region_name": ern,
        "effective_channel_code": ecc,
        "effective_channel_name": ecn,
        "used_global_fallback_region": used_global_fallback_region,
        "used_global_fallback_channel": used_global_fallback_channel,
        "source_region_resolution_message": source_region_resolution_message,
        "source_channel_resolution_message": source_channel_resolution_message,
    }


def resolve_customer_for_plan(
    ctx: DSIPlanBuildContext,
    *,
    source_id: int | None,
    customer_raw: str | None,
    dealer_group_raw: str | None,
) -> tuple[int | None, list[str]]:
    return _resolve_customer_from_cache(
        source_id=source_id,
        distributor_id=None,
        customer_raw=customer_raw,
        dealer_group_raw=dealer_group_raw,
        channel_raw=None,
        open_flag_raw=None,
        res_cache=ctx.res_cache,
    )
