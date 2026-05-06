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
from app.models.import_distributor_si import ChannelSourceTokenAlias, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
)
from app.services.imports.distributor_sales_inventory import (
    _load_product_resolution_index,
    _norm_key,
    _resolve_customer,
    _resolve_distributor,
    _resolve_product,
    effective_dsi_customer_primary_for_resolution,
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

def _resolve_dim_region_from_source(session: Session, raw: str | None) -> tuple[int | None, str | None]:
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
    return None, "no_catalog_match"


def _alias_channel_id_for_dsi(session: Session, source_id: int | None, normalized_token: str) -> tuple[int | None, str | None]:
    """Match distributor alias semantics: global + source-specific rows; exact normalized token only."""
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
            rid, reason = _resolve_dim_region_from_source(session, raw_pick)
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
    source_definition_id: int | None = None,
) -> dict[str, Any]:
    """Shared by resolution plan rows and bulk provisional customer preview/apply."""
    ctx = cand.context if isinstance(cand.context, dict) else {}
    src_def = source_definition_id if source_definition_id is not None else cand.source_definition_id
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
) -> dict[str, Any]:
    """Return one plan row dict for a candidate (sync Session)."""
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

    # --- distributor_token ---
    if cand.entity_type == "distributor_token":
        raw = dsi_first_sample(cand)
        nt = _norm_key(raw or cand.normalized_key or "")
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
            return {
                **base,
                "suggested_action": "resolve_product",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Multiple eligible Product Master matches — ambiguous; steward must choose product",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if pstatus == "inactive_only" or ctx.get("product_inactive_matches"):
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

        pid, perr, tag, _ev = _resolve_product(raw, prod_idx, None)
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
        if ctx.get("strategic_channel_hint"):
            geo_s = derive_effective_provisional_customer_geo_sync(
                session,
                cand,
                default_region_id=default_region_id,
                default_channel_id=default_channel_id,
                source_definition_id=source_def_id,
            )
            return {
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
            }

        samples = ctx.get("source_customer_name_raw_samples")
        cust_first = samples[0] if isinstance(samples, list) and samples and isinstance(samples[0], str) else None
        dg_raw = ctx.get("dealer_group_account_raw") if isinstance(ctx.get("dealer_group_account_raw"), str) else None
        if not dg_raw and cand.dealer_group_token:
            dg_raw = str(cand.dealer_group_token)

        primary, _notes = effective_dsi_customer_primary_for_resolution(cust_first, dg_raw)
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
            return {
                **base,
                "suggested_action": "map_customer",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.9,
                "reason": f"Matched existing customer ({','.join(diag)})",
                "suggested_target_id": int(rcid),
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if "ambiguous_customer_name" in diag:
            return {
                **base,
                "suggested_action": "map_customer",
                "plan_status": "needs_review",
                "ready": False,
                "confidence": 0.2,
                "reason": "Ambiguous customer name match — pick customer manually",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }
        if "customer_token_placeholder" in diag or "missing_customer_token" in diag:
            return {
                **base,
                "suggested_action": "ignore",
                "plan_status": "ready",
                "ready": True,
                "confidence": 0.7,
                "reason": "Blank or placeholder customer evidence — ignore candidate",
                "suggested_target_id": None,
                "needs_defaults": False,
                "needs_confirm_suspicious_distributor": False,
            }

        geo = derive_effective_provisional_customer_geo_sync(
            session,
            cand,
            default_region_id=default_region_id,
            default_channel_id=default_channel_id,
            source_definition_id=source_def_id,
        )
        geo_conflict = bool(geo.get("provisional_region_conflict") or geo.get("provisional_channel_conflict"))
        if geo_conflict:
            which: list[str] = []
            if geo.get("provisional_region_conflict"):
                which.append("region/province")
            if geo.get("provisional_channel_conflict"):
                which.append("channel/route-to-market")
            return {
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
            }

        detail_bits: list[str] = []
        if geo.get("source_region_resolution_detail"):
            detail_bits.append(f"region: {geo['source_region_resolution_detail']}")
        if geo.get("source_channel_resolution_detail"):
            detail_bits.append(f"channel: {geo['source_channel_resolution_detail']}")
        reason = "No existing customer match — propose provisional account + source alias"
        if detail_bits:
            reason += " (" + "; ".join(detail_bits) + ")"

        return {
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
        }

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


def _baseline_annotate(row: dict[str, Any]) -> dict[str, Any]:
    """Attach baseline_* copies for UI (generate path; same keys as effective merge)."""
    return {
        **row,
        "baseline_suggested_action": row.get("suggested_action"),
        "baseline_ready": row.get("ready"),
        "baseline_target_id": row.get("suggested_target_id"),
        "hold_for_manual_review": False,
        "resolution_blockers": [],
    }


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
    if candidate_ids:
        q = q.where(ImportEntityMappingCandidate.id.in_(candidate_ids))
    cands = list(session.scalars(q.order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.id)).all())
    prod_idx = _load_product_resolution_index(session)
    rows = [
        _baseline_annotate(
            plan_dsi_candidate_sync(session, c, job, prod_idx, default_region_id=default_region_id, default_channel_id=default_channel_id)
        )
        for c in cands
    ]
    ready_n = sum(1 for r in rows if r.get("ready"))
    return {
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


def _product_resolve_needs_ineligible_confirm(ctx: dict[str, Any]) -> bool:
    return ctx.get("product_match_status") == "inactive_only" or bool(ctx.get("product_inactive_matches"))


def merge_resolution_plan_row_for_apply(
    *,
    cand: ImportEntityMappingCandidate,
    base: dict[str, Any],
    ov: dict[str, Any] | None,
    default_region_id: int | None,
    default_channel_id: int | None,
    global_confirm_suspicious_distributor: bool,
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
        if _product_resolve_needs_ineligible_confirm(ctx):
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
        if geo_conflict:
            if ov is None or ov.get("region_id") is None or ov.get("channel_id") is None:
                blockers.append("provisional_geo_conflict_requires_row_region_channel_override")
        if ctx.get("strategic_channel_hint") and not (ov and ov.get("ack_strategic_channel_hint")):
            blockers.append("strategic_channel_hint_ack_required")

    if action == "create_provisional_distributor":
        if distributor_token_is_placeholder_like(cand) and not confirm_suspicious:
            blockers.append("placeholder_like_distributor_requires_confirm")

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
    by_cid: dict[int, dict[str, Any]] = {}
    for o in overrides:
        cid = int(o["candidate_id"])
        rest = {k: v for k, v in o.items() if k != "candidate_id"}
        by_cid[cid] = {**by_cid.get(cid, {}), **rest}
    q = select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
    if candidate_ids:
        q = q.where(ImportEntityMappingCandidate.id.in_(candidate_ids))
    cands = list(
        session.scalars(q.order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.id)).all()
    )
    prod_idx = _load_product_resolution_index(session)
    rows: list[dict[str, Any]] = []
    for c in cands:
        base = plan_dsi_candidate_sync(
            session, c, job, prod_idx, default_region_id=default_region_id, default_channel_id=default_channel_id
        )
        ov = by_cid.get(int(c.id))
        merged = merge_resolution_plan_row_for_apply(
            cand=c,
            base=base,
            ov=ov,
            default_region_id=default_region_id,
            default_channel_id=default_channel_id,
            global_confirm_suspicious_distributor=global_confirm_suspicious_distributor,
        )
        rows.append(_attach_effective_fields_to_row(base, c, merged))
    ready_n = sum(1 for r in rows if r.get("ready"))
    hold_n = sum(1 for r in rows if r.get("hold_for_manual_review"))
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
) -> dict[str, Any]:
    """Recompute baseline plan per id, merge overrides, then execute steward ops when effectively ready."""

    def _plan_sync(sess: Session, cid: int, jid: int, dr: int | None, dc: int | None) -> dict[str, Any] | None:
        job = sess.get(ImportJob, jid)
        cand = sess.get(ImportEntityMappingCandidate, cid)
        if not job or not cand or cand.import_job_id != jid:
            return None
        prod_idx = _load_product_resolution_index(sess)
        return plan_dsi_candidate_sync(sess, cand, job, prod_idx, default_region_id=dr, default_channel_id=dc)

    by_cid: dict[int, dict[str, Any]] = {}
    if overrides:
        for raw in overrides:
            cid = int(raw["candidate_id"])
            rest = {k: v for k, v in raw.items() if k != "candidate_id"}
            by_cid[cid] = {**by_cid.get(cid, {}), **rest}

    results: list[dict[str, Any]] = []
    applied_n = 0
    failed_n = 0
    skipped_hold_n = 0
    skipped_not_ready_n = 0

    for cid in candidate_ids:
        row = await db.run_sync(
            lambda s, c=cid, j=job_id, dr=default_region_id, dc=default_channel_id: _plan_sync(s, c, j, dr, dc)
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

