"""Multi-source region evidence for DSI customer_dealer_token candidates (hints only — no channel→region mapping)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimRegion, DistributorLocation
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.reference.iso3166_countries import resolve_alpha2_from_token
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_plan_build_context import DSIPlanBuildContext
from app.services.imports.dsi_resolution_plan import (
    derive_effective_provisional_customer_geo_sync,
    dsi_geo_channel_alias_source_id,
)
from app.services.imports.dsi_geo_resolution_cache import (
    DSIGeoResolutionCache,
    resolve_source_geo_from_ctx_cached,
)
from app.services.imports.dsi_region_catalog import suggest_region_id_for_iso_code


@dataclass
class RegionEvidenceBatchContext:
    geo_cache: DSIGeoResolutionCache
    region_code_lower: dict[str, int]
    distributor_primary_country: dict[int, str]
    peer_region_by_dealer_group: dict[str, int]
    peer_region_job_plurality: int | None


def _region_brief(plan_ctx: DSIPlanBuildContext | None, session: Session, region_id: int | None) -> tuple[str | None, str | None]:
    if region_id is None:
        return None, None
    if plan_ctx is not None:
        r = plan_ctx.regions_by_id.get(int(region_id))
        if r:
            return r.code, r.name
    from app.models.dimensions import DimRegion

    row = session.get(DimRegion, int(region_id))
    if row:
        return row.code, row.name
    return None, None


def build_region_evidence_batch_context(
    session: Session,
    job: ImportJob,
    customer_candidates: list[ImportEntityMappingCandidate],
) -> RegionEvidenceBatchContext:
    from app.services.imports.dsi_geo_resolution_cache import (
        DSIGeoResolutionCache,
        collect_geo_tokens_from_candidates,
    )

    geo_cache = DSIGeoResolutionCache.build(session)
    geo_cache.preload_aliases(collect_geo_tokens_from_candidates(customer_candidates, job))

    regions = list(session.scalars(select(DimRegion)).all())
    region_code_lower: dict[str, int] = {}
    for r in regions:
        ck = (r.code or "").strip().lower()
        if ck:
            region_code_lower[ck] = int(r.id)

    dist_ids: set[int] = set()
    for cand in customer_candidates:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        dom = ctx.get("dominant_distributor_id")
        if dom is not None:
            try:
                dist_ids.add(int(dom))
            except (TypeError, ValueError):
                pass

    distributor_primary_country: dict[int, str] = {}
    if dist_ids:
        locs = session.scalars(
            select(DistributorLocation).where(
                DistributorLocation.distributor_id.in_(list(dist_ids)),
                DistributorLocation.is_active.is_(True),
            )
        ).all()
        by_dist: dict[int, list[DistributorLocation]] = {}
        for loc in locs:
            by_dist.setdefault(int(loc.distributor_id), []).append(loc)
        for did, rows in by_dist.items():
            pick = rows[0]
            cc = (pick.country_code or "").strip().upper()
            if len(cc) == 2:
                distributor_primary_country[did] = cc

    peer_region_by_dealer_group: dict[str, int] = {}
    region_counts: dict[int, int] = {}
    src_def = dsi_geo_channel_alias_source_id(customer_candidates[0], job) if customer_candidates else None

    for cand in customer_candidates:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        geo = resolve_source_geo_from_ctx_cached(geo_cache, ctx, source_definition_id=src_def)
        rid = geo.get("source_region_resolved_id")
        if rid is None:
            continue
        try:
            rid_i = int(rid)
        except (TypeError, ValueError):
            continue
        region_counts[rid_i] = region_counts.get(rid_i, 0) + 1
        dg = (cand.dealer_group_token or "").strip()
        if dg and dg not in peer_region_by_dealer_group:
            peer_region_by_dealer_group[dg] = rid_i

    peer_plurality: int | None = None
    if region_counts:
        peer_plurality = max(region_counts, key=lambda k: region_counts[k])

    return RegionEvidenceBatchContext(
        geo_cache=geo_cache,
        region_code_lower=region_code_lower,
        distributor_primary_country=distributor_primary_country,
        peer_region_by_dealer_group=peer_region_by_dealer_group,
        peer_region_job_plurality=peer_plurality,
    )


def build_customer_region_evidence(
    session: Session,
    cand: ImportEntityMappingCandidate,
    job: ImportJob,
    *,
    plan_ctx: DSIPlanBuildContext | None = None,
    batch: RegionEvidenceBatchContext | None = None,
    default_region_id: int | None = None,
) -> dict[str, Any]:
    """Explainable region suggestion for one customer candidate (does not mutate dimensions)."""
    if cand.entity_type != "customer_dealer_token":
        return {
            "suggested_region_id": None,
            "confidence": 0.0,
            "explanation_summary": "Region evidence applies to customer candidates only.",
            "explanation_factors": [],
            "channel_geographic_hints": [],
            "province_evidence": {},
        }

    ctx = cand.context if isinstance(cand.context, dict) else {}
    cand_row_count = int(cand.row_count or 0)
    src_def = dsi_geo_channel_alias_source_id(cand, job)

    if batch is None:
        batch = build_region_evidence_batch_context(session, job, [cand])

    if plan_ctx is not None:
        from app.services.imports.dsi_plan_build_context import derive_effective_provisional_customer_geo_for_plan

        geo = derive_effective_provisional_customer_geo_for_plan(
            plan_ctx,
            cand,
            default_region_id=default_region_id,
            default_channel_id=None,
            import_job=job,
        )
    else:
        geo = derive_effective_provisional_customer_geo_sync(
            session,
            cand,
            default_region_id=default_region_id,
            default_channel_id=None,
            import_job=job,
        )

    raw_geo = resolve_source_geo_from_ctx_cached(batch.geo_cache, ctx, source_definition_id=src_def)
    factors: list[dict[str, Any]] = []
    channel_hints: list[dict[str, Any]] = []
    best_id: int | None = None
    best_conf = 0.0

    src_r = raw_geo.get("source_region_resolved_id")
    if src_r is not None:
        try:
            best_id = int(src_r)
            best_conf = 0.95
            rc, rn = _region_brief(plan_ctx, session, best_id)
            factors.append(
                {
                    "source": "province_column",
                    "detail": "resolved_from_file",
                    "region_id": best_id,
                    "region_code": rc,
                    "token": raw_geo.get("source_region_raw_token"),
                }
            )
        except (TypeError, ValueError):
            pass
    elif isinstance(raw_geo.get("source_region_raw_token"), str) and raw_geo.get("source_region_raw_token", "").strip():
        factors.append(
            {
                "source": "province_column",
                "detail": str(raw_geo.get("source_region_resolution_detail") or "unresolved"),
                "token": raw_geo.get("source_region_raw_token"),
            }
        )

    ch_samples = ctx.get("source_channel_raw_samples") or []
    if not isinstance(ch_samples, list):
        ch_samples = []
    seen_ch: set[str] = set()
    for raw_t in ch_samples:
        if not isinstance(raw_t, str):
            continue
        rt = raw_t.strip()
        if not rt:
            continue
        nk = _norm_key(rt)
        if nk in seen_ch:
            continue
        seen_ch.add(nk)
        iso = resolve_alpha2_from_token(rt)
        if not iso:
            continue
        matched_id = suggest_region_id_for_iso_code(batch.region_code_lower, iso)
        channel_hints.append(
            {
                "raw_token": rt[:512],
                "normalized_token": nk,
                "guessed_region_code": iso,
                "matched_catalog": matched_id is not None,
                "region_id": matched_id,
                "row_count": cand_row_count,
            }
        )
        if matched_id is not None and best_conf < 0.82:
            best_id = matched_id
            best_conf = 0.82 if len(rt) <= 3 else 0.78
            reg_code, reg_name = _region_brief(plan_ctx, session, matched_id)
            factors.append(
                {
                    "source": "channel_geographic_hint",
                    "detail": "channel_token_looks_like_country_not_rtm_mapping",
                    "region_id": matched_id,
                    "region_code": reg_code,
                    "token": rt[:512],
                }
            )

    dom = ctx.get("dominant_distributor_id")
    if dom is not None:
        try:
            did = int(dom)
            cc = batch.distributor_primary_country.get(did)
            if cc:
                rid = suggest_region_id_for_iso_code(batch.region_code_lower, cc)
                if rid is not None and best_conf < 0.72:
                    best_id = rid
                    best_conf = 0.72
                    rc, rn = _region_brief(plan_ctx, session, rid)
                    factors.append(
                        {
                            "source": "distributor_location",
                            "detail": f"primary_location_country_code={cc}",
                            "region_id": rid,
                            "region_code": rc,
                        }
                    )
        except (TypeError, ValueError):
            pass

    dg = (cand.dealer_group_token or "").strip()
    if dg and dg in batch.peer_region_by_dealer_group and best_conf < 0.68:
        rid = batch.peer_region_by_dealer_group[dg]
        best_id = rid
        best_conf = 0.68
        rc, rn = _region_brief(plan_ctx, session, rid)
        factors.append(
            {
                "source": "peer_customer_dealer_group",
                "detail": "same_dealer_group_has_resolved_region_on_job",
                "region_id": rid,
                "region_code": rc,
            }
        )

    if best_id is None and batch.peer_region_job_plurality is not None and best_conf < 0.55:
        rid = batch.peer_region_job_plurality
        best_id = rid
        best_conf = 0.55
        rc, rn = _region_brief(plan_ctx, session, rid)
        factors.append(
            {
                "source": "peer_customers_job_plurality",
                "detail": "most_common_resolved_region_on_this_import_job",
                "region_id": rid,
                "region_code": rc,
            }
        )

    if geo.get("used_global_fallback_region") and default_region_id is not None and best_id is None:
        best_id = int(default_region_id)
        best_conf = 0.45
        rc, rn = _region_brief(plan_ctx, session, best_id)
        factors.append(
            {
                "source": "job_fallback",
                "detail": "steward_enabled_operating_region_fallback",
                "region_id": best_id,
                "region_code": rc,
            }
        )

    province_evidence = {
        "raw_token": raw_geo.get("source_region_raw_token"),
        "resolved_id": raw_geo.get("source_region_resolved_id"),
        "detail": raw_geo.get("source_region_resolution_detail"),
    }

    if best_id is not None:
        rc, rn = _region_brief(plan_ctx, session, best_id)
        summary = f"Suggested region: {rc or '?'}" + (f" — {rn}" if rn else "")
    elif channel_hints:
        summary = "Channel values may include country hints — register region or enable job fallback."
    elif factors:
        summary = "Region evidence present but no catalog match yet."
    else:
        summary = "No region evidence — province empty and no corroborating hints."

    return {
        "suggested_region_id": best_id,
        "confidence": round(best_conf, 3),
        "explanation_summary": summary,
        "explanation_factors": factors,
        "channel_geographic_hints": channel_hints,
        "province_evidence": province_evidence,
    }


def build_job_region_evidence_batch(
    session: Session,
    job: ImportJob,
    candidates: list[ImportEntityMappingCandidate],
    *,
    plan_ctx: DSIPlanBuildContext | None = None,
    default_region_id: int | None = None,
) -> dict[int, dict[str, Any]]:
    customer_cands = [c for c in candidates if c.entity_type == "customer_dealer_token"]
    if not customer_cands:
        return {}
    batch = build_region_evidence_batch_context(session, job, customer_cands)
    out: dict[int, dict[str, Any]] = {}
    for cand in customer_cands:
        out[int(cand.id)] = build_customer_region_evidence(
            session,
            cand,
            job,
            plan_ctx=plan_ctx,
            batch=batch,
            default_region_id=default_region_id,
        )
    return out
