"""Job-scoped DSI steward resolution plan: suggest actions per candidate (transient, regenerate anytime).

Reuses the same resolution rules as validation/steward flows via distributor_sales_inventory helpers.
Does not persist plans to the database (no migration).
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimRegion
from app.models.import_distributor_si import ChannelSourceTokenAlias, ImportEntityMappingCandidate, RegionSourceTokenAlias
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _load_product_resolution_index,
    _norm_key,
    _resolve_customer,
    _resolve_distributor,
    _resolve_product,
    dsi_historical_product_eligibility_relaxed_from_import_job,
    dsi_historical_workflow_from_import_job,
    effective_dsi_customer_primary_for_resolution,
)
from app.services.imports.dsi_plan_build_context import (
    DSIPlanBuildContext,
    build_dsi_plan_build_context,
    derive_effective_provisional_customer_geo_for_plan,
    resolve_customer_for_plan,
    resolve_distributor_for_plan,
)
from app.services.imports.dsi_steward_candidate_ops import (
    DISTRIBUTOR_PROVISIONAL_SUSPICIOUS,
    StewardOpError,
    _first_sample_raw as dsi_first_sample,
    execute_create_provisional_dsi_customer,
    execute_create_provisional_dsi_distributor,
    execute_ignore_dsi_candidate,
    execute_map_dsi_customer,
    execute_map_dsi_distributor,
    execute_resolve_dsi_product,
)

PlanStatus = Literal["ready", "needs_review", "needs_defaults"]
SuggestedAction = Literal[
    "map_distributor",
    "create_provisional_distributor",
    "map_customer",
    "create_provisional_customer",
    "resolve_product",
    "ignore",
    "none",
]


def _resolve_dim_region_from_source(
    session: Session, raw: str | None, *, source_definition_id: int | None = None
) -> tuple[int | None, str | None]:
    s = (raw or "").strip()
    if not s:
        return None, "blank"
    row = session.scalar(select(DimRegion).where(func.lower(DimRegion.code) == s.lower()))
    if row is not None:
        return int(row.id), None
    nk = _norm_key(s)
    row = session.scalar(select(DimRegion).where(func.lower(DimRegion.name) == nk))
    if row is not None:
        return int(row.id), None

    rid, alias_reason = _alias_region_id_for_dsi(session, source_definition_id, nk)
    if rid is not None:
        return rid, alias_reason or "source_region_token_alias"
    if alias_reason == "conflicting_region_token_aliases":
        return None, alias_reason
    return None, "no_catalog_match"


def dsi_geo_channel_alias_source_id(
    cand: ImportEntityMappingCandidate,
    import_job: ImportJob | None,
) -> int | None:
    """SourceDefinition id used for ``channel_source_token_alias`` / ``region_source_token_alias`` lookups.

    Prefer ``cand.source_definition_id`` (persisted on the aggregate candidate when the import ran).
    If missing (older rows / repairs), fall back to ``import_job.source`` when the job is loaded.

    If both are missing, returns ``None``: the alias query considers **all** approved rows for the
    normalized token regardless of ``source_definition_id``; multiple distinct dimension ids
    yield conflicting alias resolution details.
    """
    sid = cand.source_definition_id
    if sid is not None:
        return int(sid)
    if import_job is not None and import_job.source is not None:
        return int(import_job.source.id)
    return None


def dsi_geo_region_alias_source_id(
    cand: ImportEntityMappingCandidate,
    import_job: ImportJob | None,
) -> int | None:
    """Same source-definition scope policy as ``dsi_geo_channel_alias_source_id`` (region aliases are parallel)."""

    return dsi_geo_channel_alias_source_id(cand, import_job)


def _alias_region_id_for_dsi(session: Session, source_id: int | None, normalized_token: str) -> tuple[int | None, str | None]:
    """Approved region aliases: exact ``normalized_token`` match only (no fuzzy matching)."""

    nt = (normalized_token or "").strip()
    if not nt:
        return None, None
    q = select(RegionSourceTokenAlias.region_id).where(
        RegionSourceTokenAlias.normalized_token == nt,
        RegionSourceTokenAlias.status == "approved",
    )
    if source_id is not None:
        q = q.where(
            or_(
                RegionSourceTokenAlias.source_definition_id.is_(None),
                RegionSourceTokenAlias.source_definition_id == source_id,
            )
        )
    rows = list(dict.fromkeys(session.scalars(q).all()))
    if len(rows) == 1:
        return int(rows[0]), "source_region_token_alias"
    if len(rows) > 1:
        return None, "conflicting_region_token_aliases"
    return None, None


def _alias_channel_id_for_dsi(session: Session, source_id: int | None, normalized_token: str) -> tuple[int | None, str | None]:
    """Approved channel aliases: exact ``normalized_token`` match only (no fuzzy matching).

    When ``source_id`` is set: match rows where ``source_definition_id`` is NULL (global) or equals
    ``source_id`` (source-scoped). Duplicate ``channel_id`` values dedupe; distinct channel ids conflict.

    When ``source_id`` is None: no source filter — any approved row for the token matches (all sources
    + global). Use only when both candidate and job source are unknown; prefer resolving source via
    ``dsi_geo_channel_alias_source_id``.
    """
    nt = (normalized_token or "").strip()
    if not nt:
        return None, None
    q = select(ChannelSourceTokenAlias.channel_id).where(
        ChannelSourceTokenAlias.normalized_token == nt,
        ChannelSourceTokenAlias.status == "approved",
    )
    if source_id is not None:
        q = q.where(
            or_(
                ChannelSourceTokenAlias.source_definition_id.is_(None),
                ChannelSourceTokenAlias.source_definition_id == source_id,
            )
        )
    rows = list(dict.fromkeys(session.scalars(q).all()))
    if len(rows) == 1:
        return int(rows[0]), "source_channel_token_alias"
    if len(rows) > 1:
        return None, "conflicting_channel_token_aliases"
    return None, None


def _resolve_dim_channel_from_source(
    session: Session,
    raw: str | None,
    *,
    source_definition_id: int | None = None,
) -> tuple[int | None, str | None]:
    s = (raw or "").strip()
    if not s:
        return None, "blank"
    row = session.scalar(select(DimChannel).where(func.lower(DimChannel.code) == s.lower()))
    if row is not None:
        return int(row.id), "catalog_match"
    nk = _norm_key(s)
    row = session.scalar(select(DimChannel).where(func.lower(DimChannel.name) == nk))
    if row is not None:
        return int(row.id), "catalog_match"

    cid, alias_reason = _alias_channel_id_for_dsi(session, source_definition_id, nk)
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


def _provisional_geo_dimension_message(
    *,
    detail: str | None,
    raw_token: str | None,
    dim_short: str,
    dim_long: str,
) -> str | None:
    """Stable, UI-safe explanation for a single region or channel dimension."""
    if not detail:
        return None
    if detail == "missing_source_evidence":
        return f"No {dim_long} value captured from the mapped file column for this customer candidate."
    if detail == "conflicting_source_evidence":
        return f"Multiple conflicting {dim_long} values in the file for this dealer group — pick catalog ids or a single fallback."
    if detail == "no_catalog_match":
        tok = (raw_token or "").strip()[:160] or "(blank)"
        return (
            f'Source {dim_short} "{tok}" has no matching catalog code/name and no approved source-token mapping — '
            f"pick a catalog row, optional global fallback, or leave unassigned."
        )
    if detail == "conflicting_channel_token_aliases":
        tok = (raw_token or "").strip()[:160] or "(token)"
        return (
            f'Source {dim_short} "{tok}" matches multiple approved channel token mappings — '
            f"fix alias data or use a row override."
        )
    if detail == "conflicting_region_token_aliases":
        tok = (raw_token or "").strip()[:160] or "(token)"
        return (
            f'Source {dim_short} "{tok}" matches multiple approved region token mappings — '
            f"fix alias data or use a row override."
        )
    if detail == "blank":
        return f"Source {dim_short} cell was empty after normalization."
    return f"{dim_long}: {detail}"


def _resolve_source_geo_from_ctx(
    session: Session,
    ctx: dict[str, Any],
    *,
    source_definition_id: int | None = None,
) -> dict[str, Any]:
    """Derive catalog IDs from aggregated DSI source region/channel evidence (per candidate context)."""
    reg_conflict = bool(ctx.get("provisional_region_conflict"))
    ch_conflict = bool(ctx.get("provisional_channel_conflict"))
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
    reg_norms = [n for n in (ctx.get("source_region_evidence_norms") or []) if isinstance(n, str) and n.strip()]
    ch_norms = [n for n in (ctx.get("source_channel_evidence_norms") or []) if isinstance(n, str) and n.strip()]
    reg_samples = ctx.get("source_region_raw_samples") or []
    ch_samples = ctx.get("source_channel_raw_samples") or []

    if reg_conflict:
        out["source_region_resolution_detail"] = "conflicting_source_evidence"
    else:
        uniq_r = sorted(set(reg_norms))
        if len(uniq_r) == 1:
            raw_pick = _pick_raw_for_norm(reg_samples if isinstance(reg_samples, list) else [], uniq_r[0])
            if raw_pick:
                out["source_region_raw_token"] = str(raw_pick).strip()[:512]
            rid, reason = _resolve_dim_region_from_source(session, raw_pick, source_definition_id=source_definition_id)
            out["source_region_resolved_id"] = rid
            if rid is None:
                out["source_region_resolution_detail"] = reason or "unresolved"
            else:
                out["source_region_resolution_detail"] = "catalog_match" if reason is None else reason
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
            cid, reason_c = _resolve_dim_channel_from_source(
                session, raw_pick_c, source_definition_id=source_definition_id
            )
            out["source_channel_resolved_id"] = cid
            if cid is None:
                out["source_channel_resolution_detail"] = reason_c or "unresolved"
            else:
                out["source_channel_resolution_detail"] = reason_c or "catalog_match"
        elif len(uniq_c) == 0:
            out["source_channel_resolution_detail"] = "missing_source_evidence"

    return out


def _dim_region_brief(session: Session, region_id: int | None) -> tuple[str | None, str | None]:
    if region_id is None:
        return None, None
    row = session.get(DimRegion, int(region_id))
    if not row:
        return None, None
    return (row.code or "")[:64], (row.name or "")[:256]


def _dim_channel_brief(session: Session, channel_id: int | None) -> tuple[str | None, str | None]:
    if channel_id is None:
        return None, None
    row = session.get(DimChannel, int(channel_id))
    if not row:
        return None, None
    return (row.code or "")[:64], (row.name or "")[:256]


def derive_effective_provisional_customer_geo_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    *,
    default_region_id: int | None,
    default_channel_id: int | None,
    import_job: ImportJob | None = None,
    geo_cache: Any | None = None,
) -> dict[str, Any]:
    """Shared by resolution plan rows and bulk provisional customer preview/apply."""
    ctx = cand.context if isinstance(cand.context, dict) else {}
    src_def = dsi_geo_channel_alias_source_id(cand, import_job)
    if geo_cache is not None:
        from app.services.imports.dsi_geo_resolution_cache import resolve_source_geo_from_ctx_cached

        geo = resolve_source_geo_from_ctx_cached(geo_cache, ctx, source_definition_id=src_def)
    else:
        geo = _resolve_source_geo_from_ctx(session, ctx, source_definition_id=src_def)
    src_r = geo.get("source_region_resolved_id")
    src_c = geo.get("source_channel_resolved_id")
    src_r = int(src_r) if src_r is not None else None
    src_c = int(src_c) if src_c is not None else None
    eff_r = src_r if src_r is not None else default_region_id
    eff_c = src_c if src_c is not None else default_channel_id
    rc, rn = _dim_region_brief(session, src_r)
    cc, cn = _dim_channel_brief(session, src_c)
    erc, ern = _dim_region_brief(session, eff_r)
    ecc, ecn = _dim_channel_brief(session, eff_c)

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

    source_region_resolution_message: str | None
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

    source_channel_resolution_message: str | None
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


ALLOWED_OVERRIDE_ACTIONS: dict[str, frozenset[str]] = {
    "distributor_token": frozenset({"ignore", "map_distributor", "create_provisional_distributor"}),
    "product_identifier": frozenset({"ignore", "resolve_product"}),
    "customer_dealer_token": frozenset({"ignore", "map_customer", "create_provisional_customer"}),
}


def distributor_token_is_placeholder_like(cand: ImportEntityMappingCandidate) -> bool:
    raw = dsi_first_sample(cand)
    nt = _norm_key(raw or cand.normalized_key or "")
    return nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS


def _terminal_candidate(cand: ImportEntityMappingCandidate) -> bool:
    return cand.status in ("resolved", "ignored", "waived_open_channel")


def _plan_common(cand: ImportEntityMappingCandidate) -> dict[str, Any]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    return {
        "candidate_id": cand.id,
        "entity_type": cand.entity_type,
        "normalized_key": cand.normalized_key,
        "candidate_status": cand.status,
        "row_count": cand.row_count,
        "total_units": float(cand.total_units) if cand.total_units is not None else None,
        "total_reported_value": float(cand.total_reported_value)
        if cand.total_reported_value is not None
        else None,
    }


def plan_dsi_candidate_sync(
    session: Session,
    cand: ImportEntityMappingCandidate,
    job: ImportJob,
    prod_idx: ProductResolutionIndex,
    *,
    default_region_id: int | None,
    default_channel_id: int | None,
    plan_ctx: DSIPlanBuildContext | None = None,
) -> dict[str, Any]:
    """Return one plan row dict for a candidate (sync Session)."""
    from app.services.imports.dsi_customer_intelligence import gate_dsi_plan_row_duplicate_review

    def _fin(row: dict[str, Any]) -> dict[str, Any]:
        return gate_dsi_plan_row_duplicate_review(cand, row)

    base = _plan_common(cand)
    if _terminal_candidate(cand):
        out = {
            **base,
            "suggested_action": "none",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": 0.0,
            "reason": "Candidate already terminal — no auto action",
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
        }
        return out

    source_def_id = job.source.id if job.source else None
    idx = plan_ctx.prod_idx if plan_ctx is not None else prod_idx

    # --- distributor_token ---
    if cand.entity_type == "distributor_token":
        raw = dsi_first_sample(cand)
        nt = _norm_key(raw or cand.normalized_key or "")
        if plan_ctx is not None:
            did, err = resolve_distributor_for_plan(plan_ctx, raw or cand.normalized_key, source_def_id)
        else:
            did, err = _resolve_distributor(session, raw or cand.normalized_key, source_def_id)
        if did is not None:
            return {
                **base,
                "suggested_action": "map_distributor",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.92,
                "reason": "Matched existing distributor (alias or dimension)",
                "suggested_target_id": int(did),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS:
            return {
                **base,
                "suggested_action": "ignore",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.75,
                "reason": "Placeholder-like distributor token — safe to ignore as junk",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
                "distributor_token_placeholder_like": True,
                "alternate_action_with_confirm_note": (
                    "Override to create provisional distributor only if you confirm placeholder-like token handling"
                ),
            }
        return {
            **base,
            "suggested_action": "create_provisional_distributor",
            "plan_status": "ready",
            "ready": True,
            "confidence": 0.55,
            "reason": "No existing distributor match — propose provisional + alias",
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
            "distributor_token_placeholder_like": False,
        }

    # --- product_identifier ---
    if cand.entity_type == "product_identifier":
        ctx = cand.context if isinstance(cand.context, dict) else {}
        raw = dsi_first_sample(cand)
        pstatus = ctx.get("product_match_status")
        if pstatus == "ambiguous_eligible":
            amb = ctx.get("product_ambiguous_eligible")
            if isinstance(amb, dict):
                eligible = amb.get("eligible_products")
                if isinstance(eligible, list) and len(eligible) == 1:
                    try:
                        sole_pid = int(eligible[0].get("product_id"))
                    except (TypeError, ValueError, AttributeError):
                        sole_pid = 0
                    if sole_pid > 0:
                        return {
                            **base,
                            "suggested_action": "resolve_product",
                            "plan_status": "ready",
                            "ready": True,
                            "confidence": 0.72,
                            "reason": "Single eligible Product Master match from validation context — propose ProductAlias bind",
                            "suggested_target_id": sole_pid,
                            "needs_defaults": False,
                            "needs_confirm_suspicious_distributor": False,
                        }
                elig_ids: list[int] = []
                for ep in eligible or []:
                    if not isinstance(ep, dict):
                        continue
                    try:
                        v = int(ep.get("product_id"))
                    except (TypeError, ValueError):
                        continue
                    if v > 0:
                        elig_ids.append(v)
                if not elig_ids:
                    for x in amb.get("product_ids") or []:
                        try:
                            v = int(x)
                        except (TypeError, ValueError):
                            continue
                        if v > 0:
                            elig_ids.append(v)
                from app.services.imports.dsi_product_shipment_tiebreak import (
                    ambiguous_product_plan_reason_from_context,
                    evidence_date_from_month,
                    parse_candidate_shipment_evidence,
                    try_shipment_tiebreak_product_id,
                )

                ship_ev = parse_candidate_shipment_evidence(ctx)
                dom = ctx.get("dominant_unresolved_distributor_id")
                try:
                    dist_id = int(dom) if dom is not None else ship_ev.dominant_unresolved_distributor_id
                except (TypeError, ValueError):
                    dist_id = ship_ev.dominant_unresolved_distributor_id
                ev_date = evidence_date_from_month(ship_ev.dominant_evidence_month)
                corr_cache = plan_ctx.shipment_corr_cache if plan_ctx is not None else None
                staging_scopes = plan_ctx.product_staging_scopes if plan_ctx is not None else None
                global_identity = (
                    plan_ctx.global_product_identity if plan_ctx is not None else None
                )
                pick, tie_src = try_shipment_tiebreak_product_id(
                    session,
                    eligible_product_ids=elig_ids,
                    raw_token=raw,
                    distributor_id=dist_id,
                    evidence_date=ev_date,
                    stored_distinct_product_ids=ship_ev.stored_distinct_product_ids,
                    corr_cache=corr_cache,
                    candidate_context=ctx,
                    normalized_key=cand.normalized_key,
                    staging_scopes=staging_scopes,
                    global_product_identity=global_identity,
                )
                if pick is not None:
                    if tie_src == "shipment_global_identity":
                        reason = (
                            "Global shipment identity: sole resolved product across all evidence — "
                            "propose ProductAlias bind"
                        )
                    else:
                        reason = (
                            f"Shipment evidence tie-break ({tie_src or 'shipment'}) — single Product Master "
                            f"match among eligible rows — propose ProductAlias bind"
                        )
                    return {
                        **base,
                        "suggested_action": "resolve_product",
                        "plan_status": "ready",
                        "ready": True,
                        "confidence": 0.78,
                        "reason": reason,
                        "suggested_target_id": int(pick),
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                    }
            dom = ctx.get("dominant_unresolved_distributor_id")
            from app.services.imports.dsi_product_running_change import (
                IGNORE_REASON_NO_CATALOGUE,
                IGNORE_REASON_SKU_INDETERMINATE,
                is_dsi_running_change_ambiguous_context,
            )
            from app.services.imports.dsi_product_shipment_tiebreak import (
                ambiguous_product_plan_reason_from_context,
                evidence_date_from_month,
                parse_candidate_shipment_evidence,
            )

            if is_dsi_running_change_ambiguous_context(ctx):
                rc = (
                    IGNORE_REASON_SKU_INDETERMINATE
                    if ctx.get("product_match_status") == "ambiguous_eligible"
                    else IGNORE_REASON_NO_CATALOGUE
                )
                return {
                    **base,
                    "suggested_action": "ignore",
                    "plan_status": "needs_review",
                    "ready": False,
                    "confidence": 0.35,
                    "reason": (
                        "Running-change / supersession token — receipt/temporal split rows by date; "
                        "token-level ProductAlias bind is blocked. Ignore indeterminate remainder or "
                        "resolve per date cluster after review."
                    ),
                    "suggested_target_id": None,
                    "needs_defaults": False,
                    "needs_confirm_suspicious_distributor": False,
                    "resolution_blockers": ["running_change_token_alias_blocked"],
                    "suggested_ignore_reason_code": rc,
                    "token_level_resolve_product_blocked": True,
                }

            ship_ev = parse_candidate_shipment_evidence(ctx)
            ev_date_plan = evidence_date_from_month(ship_ev.dominant_evidence_month)
            if dsi_historical_workflow_from_import_job(job) and dom is not None and plan_ctx is None:
                pid_h, perr_h, tag_h, _ev_h = _resolve_product(
                    raw,
                    idx,
                    ev_date_plan,
                    relax_inactive_dim_product_for_historical_dsi=dsi_historical_product_eligibility_relaxed_from_import_job(
                        job
                    ),
                    db=session,
                    distributor_id=int(dom),
                )
                if pid_h is not None and perr_h is None:
                    return {
                        **base,
                        "suggested_action": "resolve_product",
                        "plan_status": "ready",
                        "ready": True,
                        "confidence": 0.65,
                        "reason": (
                            f"Historical workflow: single corroborated Product Master match ({tag_h or 'resolved'}) "
                            f"after shipment/disambiguation — propose ProductAlias bind"
                        ),
                        "suggested_target_id": int(pid_h),
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                    }
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": ambiguous_product_plan_reason_from_context(ctx),
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if pstatus == "inactive_only" or ctx.get("product_inactive_matches"):
            if dsi_historical_product_eligibility_relaxed_from_import_job(job):
                pid_r, perr_r, tag_r, _ev_r = _resolve_product(
                    raw,
                    idx,
                    None,
                    relax_inactive_dim_product_for_historical_dsi=True,
                )
                if pid_r is not None and perr_r is None:
                    return {
                        **base,
                        "suggested_action": "resolve_product",
                        "plan_status": "ready",
                        "ready": True,
                        "confidence": 0.88,
                        "reason": f"Single Product Master match ({tag_r or 'resolved'}) — propose ProductAlias bind",
                        "suggested_target_id": int(pid_r),
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                    }
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.25,
                "reason": "Inactive/ineligible matches only — confirm product + audit note in steward UI",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }

        pid, perr, tag, _ev = _resolve_product(
            raw,
            idx,
            None,
            relax_inactive_dim_product_for_historical_dsi=dsi_historical_product_eligibility_relaxed_from_import_job(job),
        )
        if pid is not None and perr is None:
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.88,
                "reason": f"Single Product Master match ({tag or 'resolved'}) — propose ProductAlias bind",
                "suggested_target_id": int(pid),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        return {
            **base,
            "suggested_action": "resolve_product",
            "plan_status": "needs_review",
            "ready": False,
            "confidence": 0.15,
            "reason": (ctx.get("product_match_summary") or perr or "No safe automatic product match"),
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
        }

    # --- customer_dealer_token ---
    if cand.entity_type == "customer_dealer_token":
        ctx = cand.context if isinstance(cand.context, dict) else {}
        if ctx.get("strategic_channel_hint") and not dsi_historical_workflow_from_import_job(job):
            if plan_ctx is not None:
                geo_s = derive_effective_provisional_customer_geo_for_plan(
                    plan_ctx,
                    cand,
                    default_region_id=default_region_id,
                    default_channel_id=default_channel_id,
                    import_job=job,
                )
            else:
                geo_s = derive_effective_provisional_customer_geo_sync(
                    session,
                    cand,
                    default_region_id=default_region_id,
                    default_channel_id=default_channel_id,
                    import_job=job,
                )
            return _fin({
                **base,
                "suggested_action": "create_provisional_customer",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Strategic / marketplace-style channel evidence — review before mapping or provisional",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
                **{k: v for k, v in geo_s.items() if k not in ("provisional_region_conflict", "provisional_channel_conflict")},
            })

        samples = ctx.get("source_customer_name_raw_samples")
        cust_first = samples[0] if isinstance(samples, list) and samples and isinstance(samples[0], str) else None
        dg_raw = ctx.get("dealer_group_account_raw") if isinstance(ctx.get("dealer_group_account_raw"), str) else None
        if not dg_raw and cand.dealer_group_token:
            dg_raw = str(cand.dealer_group_token)

        primary, _notes = effective_dsi_customer_primary_for_resolution(cust_first, dg_raw)
        dist_id: int | None = None
        dom = ctx.get("dominant_distributor_id")
        if dom is not None:
            try:
                dist_id = int(dom)
            except (TypeError, ValueError):
                dist_id = None

        if plan_ctx is not None:
            from app.services.imports.dsi_customer_intelligence import (
                lookup_historical_customer_resolution,
                resolve_customer_id_distributor_scoped_alias,
            )

            from app.services.imports.dsi_customer_intelligence import (
                lookup_job_customer_sibling_mapping,
            )
            from app.services.imports.dsi_customer_name_normalization import (
                normalize_customer_name_for_similarity,
            )

            hist = lookup_historical_customer_resolution(
                plan_ctx.historical_customers,
                distributor_id=dist_id,
                normalized_key=str(cand.normalized_key or ""),
                customer_raw=primary,
                dealer_group_raw=dg_raw,
            )
            if hist is not None:
                ctx_hist = cand.context if isinstance(cand.context, dict) else {}
                if ctx_hist.get("conflict_flag"):
                    return _fin({
                        **base,
                        "suggested_action": "map_customer",
                        "plan_status": "needs_review",
                        "ready": False,
                        "confidence": 0.15,
                        "reason": (
                            "Prior steward resolutions disagree for this token — "
                            "choose the correct customer manually"
                        ),
                        "suggested_target_id": None,
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                        "conflict_flag": True,
                        "prior_resolution_conflict": ctx_hist.get("prior_resolution_conflict"),
                    })
                tier = "none"
                sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
                intel = sm.get("intelligence_state")
                if isinstance(intel, dict):
                    tier = str(intel.get("auto_resolution_tier") or "none").strip().lower()
                weekly_mode = not dsi_historical_workflow_from_import_job(job)
                if weekly_mode and tier == "supervised":
                    from app.models.dimensions import DimCustomer

                    label_row = session.get(DimCustomer, int(hist.customer_id))
                    target_label = None
                    if label_row is not None:
                        target_label = (label_row.name or label_row.code or "")[:256] or None
                    return _fin({
                        **base,
                        "suggested_action": "map_customer",
                        "plan_status": "ready",
                        "ready": True,
                        "confidence": float(hist.confidence),
                        "reason": (
                            f"Previously resolved on import job {hist.import_job_id} "
                            f"({hist.resolution_kind}) — review before apply (supervised auto-resolution)"
                        ),
                        "suggested_target_id": int(hist.customer_id),
                        "suggested_target_label": target_label,
                        "auto_resolved_supervised": True,
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                        "historical_resolution": {
                            "label": "previously_resolved_supervised",
                            "import_job_id": hist.import_job_id,
                            "customer_id": hist.customer_id,
                            "match_reason": hist.match_reason,
                            "resolution_kind": hist.resolution_kind,
                            "confidence": float(hist.confidence),
                        },
                    })
                return _fin({
                    **base,
                    "suggested_action": "map_customer",
                    "plan_status": "needs_review",
                    "ready": False,
                    "confidence": float(hist.confidence),
                    "reason": (
                        f"Previously resolved on import job {hist.import_job_id} "
                        f"({hist.resolution_kind}) — confirm before applying"
                    ),
                    "suggested_target_id": int(hist.customer_id),
                    "needs_defaults": False,
                    "needs_confirm_suspicious_distributor": False,
                    "historical_resolution": {
                        "label": "previously_resolved",
                        "import_job_id": hist.import_job_id,
                        "customer_id": hist.customer_id,
                        "match_reason": hist.match_reason,
                        "resolution_kind": hist.resolution_kind,
                        "confidence": float(hist.confidence),
                    },
                })
            if dist_id is not None and primary:
                scoped_cid = resolve_customer_id_distributor_scoped_alias(
                    plan_ctx.res_cache,
                    source_id=source_def_id,
                    distributor_id=dist_id,
                    normalized_customer=_norm_key(primary),
                )
                if scoped_cid is not None:
                    return _fin({
                        **base,
                        "suggested_action": "map_customer",
                        "plan_status": "ready",
                        "ready": True,
                        "confidence": 0.93,
                        "reason": "Matched approved customer alias for this distributor (stronger than generic alias)",
                        "suggested_target_id": int(scoped_cid),
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                        "resolution_signal": "distributor_scoped_alias",
                    })
            dg_norm = normalize_customer_name_for_similarity(dg_raw) if dg_raw else ""
            sibling = lookup_job_customer_sibling_mapping(
                plan_ctx.job_customer_siblings_by_dealer_group,
                dealer_group_norm=dg_norm,
                exclude_normalized_key=str(cand.normalized_key or ""),
            )
            if sibling is not None:
                from app.services.merge_redirect import follow_customer_merge_redirect_sync

                sibling_cid = follow_customer_merge_redirect_sync(session, int(sibling.customer_id))
                return _fin({
                    **base,
                    "suggested_action": "map_customer",
                    "plan_status": "needs_review",
                    "ready": False,
                    "confidence": 0.82,
                    "reason": (
                        f"Another token on this import job ({sibling.normalized_key}) already maps to "
                        f"customer {sibling_cid} — confirm before applying"
                    ),
                    "suggested_target_id": int(sibling_cid) if sibling_cid is not None else int(sibling.customer_id),
                    "needs_defaults": False,
                    "needs_confirm_suspicious_distributor": False,
                    "sibling_mapping_hint": {
                        "normalized_key": sibling.normalized_key,
                        "customer_id": int(sibling_cid) if sibling_cid is not None else int(sibling.customer_id),
                        "match_reason": sibling.match_reason,
                    },
                })
            rcid, diag = resolve_customer_for_plan(
                plan_ctx,
                source_id=source_def_id,
                customer_raw=primary,
                dealer_group_raw=dg_raw,
            )
            if rcid is None and primary:
                from app.services.imports.dsi_customer_name_normalization import (
                    unique_sim_customer_id,
                )

                sim_cid, sim_signal = unique_sim_customer_id(
                    plan_ctx.res_cache.customer_sim_name_to_ids,
                    primary,
                )
                if sim_cid is not None and sim_signal:
                    if sim_signal == "similar_customer_name_trading_as_legal":
                        reason = (
                            "Matched existing customer on trading-as legal name "
                            "(unique, legal-suffix/punctuation-insensitive)"
                        )
                    elif sim_signal == "similar_customer_name_trading_as_trade":
                        reason = (
                            "Matched existing customer on trading-as trade name "
                            "(unique, legal-suffix/punctuation-insensitive)"
                        )
                    else:
                        reason = (
                            "Matched existing customer on normalized name "
                            "(legal-suffix/punctuation-insensitive)"
                        )
                    return _fin({
                        **base,
                        "suggested_action": "map_customer",
                        "plan_status": "ready",
                        "ready": True,
                        "confidence": 0.9,
                        "reason": reason,
                        "suggested_target_id": int(sim_cid),
                        "needs_defaults": False,
                        "needs_confirm_suspicious_distributor": False,
                        "resolution_signal": sim_signal,
                    })
        else:
            rcid, diag = _resolve_customer(
                session,
                source_id=source_def_id,
                distributor_id=None,
                customer_raw=primary,
                dealer_group_raw=dg_raw,
                channel_raw=None,
                open_flag_raw=None,
            )
        if rcid is not None:
            return _fin({
                **base,
                "suggested_action": "map_customer",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.9,
                "reason": f"Matched existing customer ({','.join(diag)})",
                "suggested_target_id": int(rcid),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            })
        if "ambiguous_customer_name" in diag:
            return _fin({
                **base,
                "suggested_action": "map_customer",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Ambiguous customer name match — pick customer manually",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            })
        if "customer_token_placeholder" in diag or "missing_customer_token" in diag:
            return _fin({
                **base,
                "suggested_action": "ignore",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.7,
                "reason": "Blank or placeholder customer evidence — ignore candidate",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            })

        if plan_ctx is not None:
            geo = derive_effective_provisional_customer_geo_for_plan(
                plan_ctx,
                cand,
                default_region_id=default_region_id,
                default_channel_id=default_channel_id,
                import_job=job,
            )
        else:
            geo = derive_effective_provisional_customer_geo_sync(
                session,
                cand,
                default_region_id=default_region_id,
                default_channel_id=default_channel_id,
                import_job=job,
            )
        geo_conflict = bool(geo.get("provisional_region_conflict") or geo.get("provisional_channel_conflict"))
        if geo_conflict and not dsi_historical_workflow_from_import_job(job):
            which: list[str] = []
            if geo.get("provisional_region_conflict"):
                which.append("region/province")
            if geo.get("provisional_channel_conflict"):
                which.append("channel/route-to-market")
            return _fin({
                **base,
                "suggested_action": "create_provisional_customer",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.35,
                "reason": (
                    "Conflicting source evidence for "
                    + " and ".join(which)
                    + " — set row region & channel overrides, change action, or map to an existing customer"
                ),
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
                **{k: v for k, v in geo.items()},
            })

        detail_bits: list[str] = []
        if geo.get("source_region_resolution_detail"):
            detail_bits.append(f"region: {geo['source_region_resolution_detail']}")
        if geo.get("source_channel_resolution_detail"):
            detail_bits.append(f"channel: {geo['source_channel_resolution_detail']}")
        reason = "No existing customer match — propose provisional account + source alias"
        if detail_bits:
            reason += " (" + "; ".join(detail_bits) + ")"

        return _fin({
            **base,
            "suggested_action": "create_provisional_customer",
            "plan_status": "ready",
            "ready": True,
            "confidence": 0.55,
            "reason": reason,
            "suggested_target_id": None,
            "needs_defaults": False,
            "needs_confirm_suspicious_distributor": False,
            **{k: v for k, v in geo.items()},
        })

    return {
        **base,
        "suggested_action": "none",
        "plan_status": "needs_review",
        "ready": False,
        "confidence": 0.0,
        "reason": "Unsupported entity_type for auto plan",
        "suggested_target_id": None,
        "needs_defaults": False,
        "needs_confirm_suspicious_distributor": False,
    }


def _infer_plan_rule_path(cand: ImportEntityMappingCandidate, row: dict[str, Any]) -> str:
    """Stable rule identifier for plan explainability (not persisted)."""
    entity = str(cand.entity_type or "")
    action = str(row.get("suggested_action") or "")
    ctx = cand.context if isinstance(cand.context, dict) else {}

    if entity == "distributor_token":
        if action == "map_distributor":
            return "distributor.alias_or_dim_match"
        if action == "ignore":
            return "distributor.placeholder_token_ignore"
        if action == "create_provisional_distributor":
            return "distributor.no_match_provisional"
        return "distributor.unsupported"

    if entity == "product_identifier":
        pstatus = ctx.get("product_match_status")
        if action == "resolve_product" and row.get("ready") is True:
            if "historical" in str(row.get("reason") or "").lower():
                return "product.historical_single_match"
            if pstatus == "ambiguous_eligible":
                return "product.ambiguous_corroborated_single"
            return "product.single_eligible_match"
        if pstatus == "ambiguous_eligible":
            return "product.ambiguous_eligible_manual"
        if pstatus == "inactive_only":
            return "product.inactive_only_confirm"
        if pstatus == "no_match":
            return "product.no_match"
        return "product.needs_review"

    if entity == "customer_dealer_token":
        if ctx.get("strategic_channel_hint"):
            return "customer.strategic_channel_review"
        if action == "map_customer":
            return "customer.alias_or_dim_match"
        if action == "create_provisional_customer":
            return "customer.no_match_provisional_geo"
        if action == "ignore":
            return "customer.ignore"
        return "customer.needs_review"

    return "unknown"


def build_plan_why_from_candidate(
    cand: ImportEntityMappingCandidate,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Structured explainability for plan rows (blockers, rule path, corroboration)."""
    ctx = cand.context if isinstance(cand.context, dict) else {}
    blockers = [str(b) for b in (row.get("resolution_blockers") or []) if b is not None and str(b).strip()]
    rule_path = _infer_plan_rule_path(cand, row)

    corroboration_hits: list[dict[str, Any]] = []
    markers = ctx.get("corroboration_markers")
    if isinstance(markers, list):
        for m in markers:
            if m is None:
                continue
            corroboration_hits.append({"marker": str(m)})

    sec = ctx.get("shipment_evidence_corroboration")
    if isinstance(sec, dict):
        corroboration_hits.append(
            {
                "marker": "shipment_evidence_corroboration",
                "kind": sec.get("kind"),
                "match_count": sec.get("best_match_count"),
                "mode": sec.get("mode"),
                "summary": sec.get("summary"),
            }
        )

    return {
        "blockers": blockers,
        "rule_path": rule_path,
        "corroboration_hits": corroboration_hits,
        "narrative": str(row.get("reason") or "").strip(),
    }


def _baseline_annotate(row: dict[str, Any], cand: ImportEntityMappingCandidate) -> dict[str, Any]:
    """Attach baseline_* copies for UI (generate path; same keys as effective merge)."""
    base_row = {
        **row,
        "baseline_suggested_action": row.get("suggested_action"),
        "baseline_ready": row.get("ready"),
        "baseline_target_id": row.get("suggested_target_id"),
        "hold_for_manual_review": False,
        "resolution_blockers": [],
    }
    base_row["plan_why"] = build_plan_why_from_candidate(cand, base_row)
    return base_row


def build_dsi_resolution_plan_sync(
    session: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None,
    default_region_id: int | None,
    default_channel_id: int | None,
) -> dict[str, Any]:
    job = session.get(ImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    q = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    plan_truncated = False
    if candidate_ids:
        q = q.where(ImportEntityMappingCandidate.id.in_(candidate_ids))
    else:
        q = q.limit(100)
        plan_truncated = True
    cands = list(session.scalars(q.order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.id)).all())
    plan_ctx = build_dsi_plan_build_context(session, current_job_id=job_id)
    from app.services.imports.dsi_customer_region_evidence import build_job_region_evidence_batch

    region_evidence_by_id = build_job_region_evidence_batch(
        session,
        job,
        cands,
        plan_ctx=plan_ctx,
        default_region_id=default_region_id,
    )
    rows = []
    for c in cands:
        if _terminal_candidate(c):
            continue
        base_row = _baseline_annotate(
            plan_dsi_candidate_sync(
                session,
                c,
                job,
                plan_ctx.prod_idx,
                default_region_id=default_region_id,
                default_channel_id=default_channel_id,
                plan_ctx=plan_ctx,
            ),
            c,
        )
        ev = region_evidence_by_id.get(int(c.id))
        if ev is not None:
            base_row["region_evidence"] = ev
        rows.append(base_row)
    ready_n = sum(1 for r in rows if r.get("ready"))
    out: dict[str, Any] = {
        "import_job_id": job_id,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ready": ready_n,
            "not_ready": len(rows) - ready_n,
            "hold": 0,
        },
        "defaults_used": {
            "region_id": default_region_id,
            "channel_id": default_channel_id,
        },
    }
    if plan_truncated:
        out["plan_scope_note"] = (
            "candidate_ids omitted — only the first 100 candidates were planned. "
            "Pass candidate_ids (e.g. current table page) for scoped planning."
        )
    from app.services.imports.dsi_plan_target_labels import enrich_plan_rows_with_target_labels

    out["rows"] = enrich_plan_rows_with_target_labels(session, rows)
    return out


def _product_resolve_needs_ineligible_confirm(ctx: dict[str, Any]) -> bool:
    return ctx.get("product_match_status") == "inactive_only" or bool(ctx.get("product_inactive_matches"))


_HISTORICAL_DETERMINISTIC_INELIGIBLE_AUTO_CONFIRM_NOTE = (
    "auto-confirmed ineligible: deterministic unique identity, historical path"
)


def _product_apply_target_is_deterministic_unique_bind(
    *,
    base: dict[str, Any],
    target_id: int | None,
) -> bool:
    """True when classify-time plan marked a sole ready resolve_product at this target (not steward guess)."""
    if target_id is None:
        return False
    try:
        tid = int(target_id)
    except (TypeError, ValueError):
        return False

    has_baseline = "baseline_ready" in base or "baseline_suggested_action" in base or "baseline_target_id" in base
    if has_baseline:
        if str(base.get("baseline_suggested_action") or "") != "resolve_product":
            return False
        if not base.get("baseline_ready"):
            return False
        bt = base.get("baseline_target_id")
        if bt is None:
            return False
        try:
            return int(bt) == tid
        except (TypeError, ValueError):
            return False

    if str(base.get("suggested_action") or "") != "resolve_product":
        return False
    if not base.get("ready"):
        return False
    bt = base.get("suggested_target_id")
    if bt is None:
        return False
    try:
        return int(bt) == tid
    except (TypeError, ValueError):
        return False


def merge_resolution_plan_row_for_apply(
    *,
    cand: ImportEntityMappingCandidate,
    base: dict[str, Any],
    ov: dict[str, Any] | None,
    default_region_id: int | None,
    default_channel_id: int | None,
    global_confirm_suspicious_distributor: bool,
    historical_dsi_workflow: bool = False,
    historical_dsi_product_eligibility_relaxed: bool = False,
) -> dict[str, Any]:
    """Single source of truth for effective action + readiness (used by /effective and /apply)."""
    blockers: list[str] = []
    hold = bool(ov and ov.get("hold_for_manual_review"))
    if hold:
        return {
            "hold_for_manual_review": True,
            "effective_action": None,
            "effective_target_id": None,
            "effective_ready": False,
            "blockers": ["hold_for_manual_review"],
            "confirm_for_suspicious_distributor_token": False,
            "confirm_ineligible_product": False,
            "audit_note": None,
            "effective_region_id": None,
            "effective_channel_id": None,
        }

    entity = str(cand.entity_type)
    base_action = str(base.get("suggested_action") or "none")
    action = base_action
    target_id: int | None
    bt = base.get("suggested_target_id")
    target_id = int(bt) if bt is not None else None

    if ov:
        if "action" in ov and ov.get("action") is not None:
            action = str(ov["action"])
        if "target_id" in ov:
            tid = ov.get("target_id")
            target_id = int(tid) if tid is not None else None

    confirm_suspicious = global_confirm_suspicious_distributor or bool(
        ov and ov.get("confirm_for_suspicious_distributor_token")
    )
    confirm_ineligible = bool(ov and ov.get("confirm_ineligible_product"))
    audit_note_raw = (ov.get("audit_note") if ov else None) or None
    audit_note = str(audit_note_raw).strip() if audit_note_raw is not None else None
    if audit_note == "":
        audit_note = None

    if action in ("none", ""):
        return {
            "hold_for_manual_review": False,
            "effective_action": action,
            "effective_target_id": target_id,
            "effective_ready": False,
            "blockers": ["no_action"],
            "confirm_for_suspicious_distributor_token": confirm_suspicious,
            "confirm_ineligible_product": confirm_ineligible,
            "audit_note": audit_note,
            "effective_region_id": None,
            "effective_channel_id": None,
        }

    allowed = ALLOWED_OVERRIDE_ACTIONS.get(entity, frozenset())
    if action not in allowed:
        return {
            "hold_for_manual_review": False,
            "effective_action": action,
            "effective_target_id": target_id,
            "effective_ready": False,
            "blockers": [f"action_not_allowed_for_entity:{entity}"],
            "confirm_for_suspicious_distributor_token": confirm_suspicious,
            "confirm_ineligible_product": confirm_ineligible,
            "audit_note": audit_note,
            "effective_region_id": None,
            "effective_channel_id": None,
        }

    ctx = cand.context if isinstance(cand.context, dict) else {}
    eff_r_apply: int | None = None
    eff_c_apply: int | None = None

    if action in ("map_distributor", "map_customer", "resolve_product"):
        if target_id is None:
            blockers.append("target_id_required")

    if action == "resolve_product":
        deterministic_unique = _product_apply_target_is_deterministic_unique_bind(
            base=base,
            target_id=target_id,
        )
        if historical_dsi_product_eligibility_relaxed and deterministic_unique:
            # Validate/plan may admit inactive targets under historical relaxation without
            # stamping inactive_only on context (e.g. resolved_unique / tie-break). Set confirm
            # here so execute_resolve_dsi_product → validate_dsi_product_resolve honors the same path.
            confirm_ineligible = True
            if audit_note is None or len(audit_note) < 8:
                audit_note = _HISTORICAL_DETERMINISTIC_INELIGIBLE_AUTO_CONFIRM_NOTE
        elif _product_resolve_needs_ineligible_confirm(ctx):
            if not confirm_ineligible or audit_note is None or len(audit_note) < 8:
                blockers.append("inactive_or_ineligible_product_requires_confirm_and_audit_note")

    if action == "create_provisional_customer":
        br = base.get("effective_region_id")
        eff_r_apply = int(br) if br is not None else None
        bc = base.get("effective_channel_id")
        eff_c_apply = int(bc) if bc is not None else None
        if ov:
            if ov.get("region_id") is not None:
                eff_r_apply = int(ov["region_id"])
            if ov.get("channel_id") is not None:
                eff_c_apply = int(ov["channel_id"])
        geo_conflict = bool(ctx.get("provisional_region_conflict") or ctx.get("provisional_channel_conflict"))
        if not historical_dsi_workflow:
            if geo_conflict:
                if ov is None or ov.get("region_id") is None or ov.get("channel_id") is None:
                    blockers.append("provisional_geo_conflict_requires_row_region_channel_override")
            if ctx.get("strategic_channel_hint") and not (ov and ov.get("ack_strategic_channel_hint")):
                blockers.append("strategic_channel_hint_ack_required")

    if action == "create_provisional_distributor":
        if (
            not historical_dsi_workflow
            and distributor_token_is_placeholder_like(cand)
            and not confirm_suspicious
        ):
            blockers.append("placeholder_like_distributor_requires_confirm")

    from app.services.imports.dsi_customer_intelligence import dsi_candidate_duplicate_review_unresolved

    if dsi_candidate_duplicate_review_unresolved(cand):
        blockers.append("duplicate_review_required")

    effective_ready = len(blockers) == 0

    return {
        "hold_for_manual_review": False,
        "effective_action": action,
        "effective_target_id": target_id,
        "effective_ready": effective_ready,
        "blockers": blockers,
        "confirm_for_suspicious_distributor_token": confirm_suspicious,
        "confirm_ineligible_product": confirm_ineligible,
        "audit_note": audit_note,
        "effective_region_id": eff_r_apply,
        "effective_channel_id": eff_c_apply,
    }


def _attach_effective_fields_to_row(
    base: dict[str, Any],
    cand: ImportEntityMappingCandidate,
    merged: dict[str, Any],
) -> dict[str, Any]:
    """Augment a baseline plan row with baseline_* copies and merged effective fields for API/UI."""
    out = {
        **base,
        "baseline_suggested_action": base.get("suggested_action"),
        "baseline_ready": base.get("ready"),
        "baseline_target_id": base.get("suggested_target_id"),
        "hold_for_manual_review": merged["hold_for_manual_review"],
        "resolution_blockers": list(merged["blockers"]),
    }
    if merged["hold_for_manual_review"]:
        out["ready"] = False
        out["plan_status"] = "needs_review"
        out["needs_confirm_suspicious_distributor"] = False
        return out

    out["suggested_action"] = merged["effective_action"]
    out["suggested_target_id"] = merged["effective_target_id"]
    out["ready"] = merged["effective_ready"]
    if merged["effective_ready"]:
        out["plan_status"] = "ready"
    else:
        out["plan_status"] = "needs_review"

    suspicious = distributor_token_is_placeholder_like(cand)
    out["needs_confirm_suspicious_distributor"] = bool(
        merged["effective_action"] == "create_provisional_distributor"
        and suspicious
        and not merged["confirm_for_suspicious_distributor_token"]
    )
    out["effective_region_id"] = merged.get("effective_region_id")
    out["effective_channel_id"] = merged.get("effective_channel_id")
    out["plan_why"] = build_plan_why_from_candidate(cand, out)
    return out


def build_dsi_resolution_plan_effective_sync(
    session: Session,
    job_id: int,
    *,
    candidate_ids: list[int] | None,
    default_region_id: int | None,
    default_channel_id: int | None,
    overrides: list[dict[str, Any]],
    global_confirm_suspicious_distributor: bool,
) -> dict[str, Any]:
    """Baseline plan rows merged with per-candidate overrides (read-only)."""
    job = session.get(ImportJob, job_id)
    if not job:
        raise ValueError("Import job not found")
    historical_wf = dsi_historical_workflow_from_import_job(job)
    historical_relaxed = dsi_historical_product_eligibility_relaxed_from_import_job(job)
    by_cid: dict[int, dict[str, Any]] = {}
    for o in overrides:
        cid = int(o["candidate_id"])
        rest = {k: v for k, v in o.items() if k != "candidate_id"}
        by_cid[cid] = {**by_cid.get(cid, {}), **rest}
    q = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    if candidate_ids:
        q = q.where(ImportEntityMappingCandidate.id.in_(candidate_ids))
    if candidate_ids:
        pass
    else:
        q = q.limit(100)
    cands = list(
        session.scalars(q.order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.id)).all()
    )
    plan_ctx = build_dsi_plan_build_context(session, current_job_id=job_id)
    from app.services.imports.dsi_customer_region_evidence import build_job_region_evidence_batch

    region_evidence_by_id = build_job_region_evidence_batch(
        session,
        job,
        cands,
        plan_ctx=plan_ctx,
        default_region_id=default_region_id,
    )
    rows: list[dict[str, Any]] = []
    for c in cands:
        if _terminal_candidate(c):
            continue
        base = plan_dsi_candidate_sync(
            session,
            c,
            job,
            plan_ctx.prod_idx,
            default_region_id=default_region_id,
            default_channel_id=default_channel_id,
            plan_ctx=plan_ctx,
        )
        ev = region_evidence_by_id.get(int(c.id))
        if ev is not None:
            base["region_evidence"] = ev
        ov = by_cid.get(int(c.id))
        merged = merge_resolution_plan_row_for_apply(
            cand=c,
            base=base,
            ov=ov,
            default_region_id=default_region_id,
            default_channel_id=default_channel_id,
            global_confirm_suspicious_distributor=global_confirm_suspicious_distributor,
            historical_dsi_workflow=historical_wf,
            historical_dsi_product_eligibility_relaxed=historical_relaxed,
        )
        rows.append(_attach_effective_fields_to_row(base, c, merged))
    ready_n = sum(1 for r in rows if r.get("ready"))
    hold_n = sum(1 for r in rows if r.get("hold_for_manual_review"))
    from app.services.imports.dsi_plan_target_labels import enrich_plan_rows_with_target_labels

    rows = enrich_plan_rows_with_target_labels(session, rows)
    return {
        "import_job_id": job_id,
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ready": ready_n,
            "not_ready": len(rows) - ready_n,
            "hold": hold_n,
        },
        "defaults_used": {
            "region_id": default_region_id,
            "channel_id": default_channel_id,
        },
    }


def collect_dsi_job_unresolved_geo_tokens_sync(session: Session, job_id: int) -> dict[str, Any]:
    """Distinct source channel / region values from customer candidates that still need steward catalog work.

    Uses the same resolution rules as the DSI plan (no fuzzy matching). Conflicting multi-value source
    evidence per candidate is omitted here — those are handled via row overrides / file fixes.
    """
    job = session.get(ImportJob, int(job_id))
    if not job:
        raise ValueError("Import job not found")
    if (job.template_slug or "") != "distributor_inventory":
        raise ValueError("Job is not a distributor sales & inventory import")

    ch_acc: dict[str, dict[str, Any]] = {}
    reg_acc: dict[str, dict[str, Any]] = {}

    cands = list(
        session.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(job_id),
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).all()
    )

    from app.services.imports.dsi_geo_resolution_cache import (
        DSIGeoResolutionCache,
        collect_geo_tokens_from_candidates,
        resolve_source_geo_from_ctx_cached,
    )

    geo_cache = DSIGeoResolutionCache.build(session)
    geo_cache.preload_aliases(collect_geo_tokens_from_candidates(cands, job))

    for cand in cands:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        sid = dsi_geo_channel_alias_source_id(cand, job)
        geo = resolve_source_geo_from_ctx_cached(geo_cache, ctx, source_definition_id=sid)
        rc = int(cand.row_count or 0)

        if not geo.get("provisional_channel_conflict"):
            ch_detail = geo.get("source_channel_resolution_detail")
            ch_id = geo.get("source_channel_resolved_id")
            raw_t = geo.get("source_channel_raw_token")
            if ch_id is None and isinstance(raw_t, str) and raw_t.strip():
                if ch_detail in ("no_catalog_match", "conflicting_channel_token_aliases"):
                    nk = _norm_key(raw_t)
                    key = f"ch:{nk}"
                    ent = ch_acc.setdefault(
                        key,
                        {
                            "dimension": "channel",
                            "normalized_token": nk,
                            "raw_token": str(raw_t).strip()[:512],
                            "resolution_detail": ch_detail,
                            "candidate_ids": [],
                            "row_count": 0,
                        },
                    )
                    ent["candidate_ids"].append(int(cand.id))
                    ent["row_count"] += rc

        if not geo.get("provisional_region_conflict"):
            reg_detail = geo.get("source_region_resolution_detail")
            rid = geo.get("source_region_resolved_id")
            raw_r = geo.get("source_region_raw_token")
            if rid is None and isinstance(raw_r, str) and raw_r.strip():
                if reg_detail in ("no_catalog_match", "conflicting_region_token_aliases"):
                    nk = _norm_key(raw_r)
                    key = f"rg:{nk}"
                    ent = reg_acc.setdefault(
                        key,
                        {
                            "dimension": "region",
                            "normalized_token": nk,
                            "raw_token": str(raw_r).strip()[:512],
                            "resolution_detail": reg_detail,
                            "candidate_ids": [],
                            "row_count": 0,
                        },
                    )
                    ent["candidate_ids"].append(int(cand.id))
                    ent["row_count"] += rc

    def _finalize(rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        from app.reference.iso3166_countries import resolve_alpha2_from_token

        region_code_lower: dict[str, int] = {}
        for r in session.scalars(select(DimRegion)).all():
            ck = (r.code or "").strip().lower()
            if ck:
                region_code_lower[ck] = int(r.id)

        out = []
        for ent in rows.values():
            ids = sorted(set(ent["candidate_ids"]))
            item: dict[str, Any] = {
                "dimension": ent["dimension"],
                "normalized_token": ent["normalized_token"],
                "raw_token": ent["raw_token"],
                "resolution_detail": ent["resolution_detail"],
                "candidate_ids": ids,
                "row_count": int(ent["row_count"]),
            }
            if ent["dimension"] == "channel":
                iso = resolve_alpha2_from_token(str(ent["raw_token"]))
                if iso:
                    alias_region_ids = geo_cache.approved_region_alias_region_ids(ent["normalized_token"])
                    catalog_rid = region_code_lower.get(iso.lower())
                    registered_rid = alias_region_ids[0] if len(alias_region_ids) == 1 else None
                    item["geographic_hint"] = {
                        "guessed_region_code": iso,
                        "matched_catalog": catalog_rid is not None,
                        "region_id": catalog_rid,
                        "alias_registered": len(alias_region_ids) > 0,
                        "registered_region_id": registered_rid,
                    }
            out.append(item)
        out.sort(key=lambda x: (x["dimension"], x["normalized_token"]))
        return out

    return {
        "import_job_id": int(job_id),
        "channels": _finalize(ch_acc),
        "regions": _finalize(reg_acc),
    }


def snapshot_product_plan_from_context(ctx: dict[str, Any] | None) -> dict[str, Any]:
    """Pure helper for tests: classify product candidate context without DB."""
    if not ctx:
        return {"plan_status": "needs_review", "ready": False}
    ps = ctx.get("product_match_status")
    if ps == "ambiguous_eligible":
        return {"plan_status": "needs_review", "ready": False, "reason": "ambiguous"}
    if ps == "inactive_only" or ctx.get("product_inactive_matches"):
        return {"plan_status": "needs_review", "ready": False, "reason": "inactive_only"}
    return {"plan_status": "unknown", "ready": False}


async def apply_dsi_resolution_plan_rows(
    db: AsyncSession,
    job_id: int,
    candidate_ids: list[int],
    *,
    default_region_id: int | None,
    default_channel_id: int | None,
    partner_tier: str | None,
    provisional_notes_summary: str | None,
    confirm_for_suspicious_distributor_token: bool,
    overrides: list[dict[str, Any]] | None = None,
    product_index: ProductResolutionIndex | None = None,
    effective_plan_rows_by_cid: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge overrides on plan rows, then execute steward ops when effectively ready.

    When ``effective_plan_rows_by_cid`` is supplied (orchestrator classify-time effective plan),
    those rows are used as the plan baseline instead of recomputing per candidate without plan_ctx.
    """

    precomputed = effective_plan_rows_by_cid or {}
    needs_replan = any(int(cid) not in precomputed for cid in candidate_ids)

    if needs_replan and product_index is None:
        product_index = await db.run_sync(_load_product_resolution_index)
    shared_prod_idx = product_index

    def _plan_sync(sess: Session, cid: int, jid: int, dr: int | None, dc: int | None) -> dict[str, Any] | None:
        job = sess.get(ImportJob, jid)
        cand = sess.get(ImportEntityMappingCandidate, cid)
        if not job or not cand or cand.import_job_id != jid:
            return None
        return plan_dsi_candidate_sync(
            sess, cand, job, shared_prod_idx, default_region_id=dr, default_channel_id=dc
        )

    by_cid: dict[int, dict[str, Any]] = {}
    if overrides:
        for raw in overrides:
            cid = int(raw["candidate_id"])
            rest = {k: v for k, v in raw.items() if k != "candidate_id"}
            by_cid[cid] = {**by_cid.get(cid, {}), **rest}

    job_hdr = await db.get(ImportJob, job_id)
    historical_wf = dsi_historical_workflow_from_import_job(job_hdr) if job_hdr else False
    historical_relaxed = (
        dsi_historical_product_eligibility_relaxed_from_import_job(job_hdr) if job_hdr else False
    )

    results: list[dict[str, Any]] = []
    applied_n = 0
    failed_n = 0
    skipped_hold_n = 0
    skipped_not_ready_n = 0

    for cid in candidate_ids:
        icid = int(cid)
        precomputed_row = precomputed.get(icid)
        if precomputed_row is not None:
            row = dict(precomputed_row)
        else:
            row = await db.run_sync(
                lambda s, c=icid, j=job_id, dr=default_region_id, dc=default_channel_id: _plan_sync(
                    s, c, j, dr, dc
                )
            )
        if row is None:
            results.append(
                {
                    "candidate_id": cid,
                    "status": "failed",
                    "detail": "Candidate not found for this job",
                }
            )
            failed_n += 1
            continue

        cand = await db.get(ImportEntityMappingCandidate, cid)
        if cand is None or cand.import_job_id != job_id:
            results.append(
                {
                    "candidate_id": cid,
                    "status": "failed",
                    "detail": "Candidate not found",
                }
            )
            failed_n += 1
            continue

        ov = by_cid.get(cid)
        merged = merge_resolution_plan_row_for_apply(
            cand=cand,
            base=row,
            ov=ov,
            default_region_id=default_region_id,
            default_channel_id=default_channel_id,
            global_confirm_suspicious_distributor=confirm_for_suspicious_distributor_token,
            historical_dsi_workflow=historical_wf,
            historical_dsi_product_eligibility_relaxed=historical_relaxed,
        )

        if merged["hold_for_manual_review"]:
            results.append(
                {
                    "candidate_id": cid,
                    "status": "skipped_hold",
                    "detail": "hold_for_manual_review",
                    "plan": row,
                    "merge": merged,
                }
            )
            skipped_hold_n += 1
            continue

        if not merged["effective_ready"]:
            results.append(
                {
                    "candidate_id": cid,
                    "status": "skipped_not_ready",
                    "detail": ",".join(merged["blockers"]) if merged["blockers"] else "not_ready",
                    "plan": row,
                    "merge": merged,
                }
            )
            skipped_not_ready_n += 1
            continue

        action = merged["effective_action"]
        try:
            if action == "ignore":
                out = await execute_ignore_dsi_candidate(db, cand, notes=None)
            elif action == "map_distributor":
                tid = merged["effective_target_id"]
                if tid is None:
                    raise StewardOpError("Plan missing distributor target", status_code=400)
                out = await execute_map_dsi_distributor(db, cand, distributor_id=int(tid), raw_token=None)
            elif action == "create_provisional_distributor":
                out = await execute_create_provisional_dsi_distributor(
                    db,
                    cand,
                    display_name_override=None,
                    distributor_code_override=None,
                    confirm_for_suspicious_token=bool(merged["confirm_for_suspicious_distributor_token"]),
                )
            elif action == "map_customer":
                tid = merged["effective_target_id"]
                if tid is None:
                    raise StewardOpError("Plan missing customer target", status_code=400)
                out = await execute_map_dsi_customer(db, cand, customer_id=int(tid), raw_token=None)
            elif action == "create_provisional_customer":
                er = merged.get("effective_region_id")
                ec = merged.get("effective_channel_id")
                out = await execute_create_provisional_dsi_customer(
                    db,
                    cand,
                    display_name_override=None,
                    region_id=int(er) if er is not None else None,
                    channel_id=int(ec) if ec is not None else None,
                    preferred_distributor_id=None,
                    partner_tier=partner_tier,
                    notes_summary=provisional_notes_summary,
                )
            elif action == "resolve_product":
                tid = merged["effective_target_id"]
                if tid is None:
                    raise StewardOpError("Plan missing product target", status_code=400)
                out = await execute_resolve_dsi_product(
                    db,
                    cand,
                    product_id=int(tid),
                    raw_token=None,
                    confirm_ineligible_product=bool(merged["confirm_ineligible_product"]),
                    audit_note=merged["audit_note"],
                    idempotency_key=None,
                )
            else:
                results.append(
                    {
                        "candidate_id": cid,
                        "status": "failed",
                        "detail": f"No executor for action {action}",
                        "plan": row,
                        "merge": merged,
                    }
                )
                failed_n += 1
                continue
            results.append(
                {"candidate_id": cid, "status": "applied", "result": out, "plan": row, "merge": merged}
            )
            applied_n += 1
        except StewardOpError as exc:
            results.append(
                {
                    "candidate_id": cid,
                    "status": "failed",
                    "detail": exc.detail,
                    "plan": row,
                    "merge": merged,
                }
            )
            failed_n += 1

    return {
        "import_job_id": job_id,
        "applied": applied_n,
        "failed": failed_n,
        "skipped_hold": skipped_hold_n,
        "skipped_not_ready": skipped_not_ready_n,
        "results": results,
    }

