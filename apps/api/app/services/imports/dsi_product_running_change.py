"""Display + steward disposition helpers for DSI running-change / supersession product tokens.

Does not alter resolver tier order or receipt/temporal logic — stats, summaries, and ignore reason codes only.
"""

from __future__ import annotations

from typing import Any

IGNORE_REASON_SKU_INDETERMINATE = "ignore_sku_indeterminate"
IGNORE_REASON_NO_CATALOGUE = "ignore_no_catalogue"
IGNORE_REASON_NO_RECEIPT_EVIDENCE = "ignore_no_receipt_evidence"

DSI_IGNORE_REASON_CODES = frozenset(
    {IGNORE_REASON_SKU_INDETERMINATE, IGNORE_REASON_NO_CATALOGUE, IGNORE_REASON_NO_RECEIPT_EVIDENCE}
)

STEWARD_IGNORED_LINE_DIAG_PREFIX = "steward_ignored_line:"

_AMBIGUOUS_PRODUCT_MATCH = "ambiguous_product_match"


def new_product_running_change_stats_bucket() -> dict[str, int]:
    return {
        "total_rows": 0,
        "resolved_receipt_temporal": 0,
        "resolved_other": 0,
        "unresolved_rows": 0,
    }


def _resolve_tag_is_receipt_or_temporal(presolve_tag: str | None) -> bool:
    tag = (presolve_tag or "").strip().lower()
    if not tag:
        return False
    if "distributor_receipt" in tag:
        return True
    if tag == "resolved_temporal_supersession":
        return True
    if "shipment_disambiguated" in tag:
        return True
    return False


def accumulate_product_running_change_stat(
    bucket: dict[str, int],
    *,
    resolved_product_id: int | None,
    presolve_tag: str | None,
) -> None:
    bucket["total_rows"] = int(bucket.get("total_rows") or 0) + 1
    if resolved_product_id is not None:
        if _resolve_tag_is_receipt_or_temporal(presolve_tag):
            bucket["resolved_receipt_temporal"] = int(bucket.get("resolved_receipt_temporal") or 0) + 1
        else:
            bucket["resolved_other"] = int(bucket.get("resolved_other") or 0) + 1
    else:
        bucket["unresolved_rows"] = int(bucket.get("unresolved_rows") or 0) + 1


def strip_ambiguous_product_match_from_diags(diag: list[str], prod_diag: list[str]) -> None:
    """Remove stale ambiguous_product_match after receipt/temporal resolve (diagnostic hygiene)."""
    while _AMBIGUOUS_PRODUCT_MATCH in prod_diag:
        prod_diag.remove(_AMBIGUOUS_PRODUCT_MATCH)
    if _AMBIGUOUS_PRODUCT_MATCH in diag:
        diag.remove(_AMBIGUOUS_PRODUCT_MATCH)


def _ambiguous_eligible_product_id_count(ctx: dict[str, Any]) -> int:
    amb = ctx.get("product_ambiguous_eligible")
    if not isinstance(amb, dict):
        return 0
    pids = amb.get("product_ids") or []
    if not isinstance(pids, list):
        return 0
    return len({int(x) for x in pids if int(x) > 0})


def is_no_receipt_evidence_ambiguous(ctx: dict[str, Any]) -> bool:
    """Model exists with 2+ eligible products but receipt tier found no evidence."""
    if ctx.get("product_match_status") != "ambiguous_eligible":
        return False
    if _ambiguous_eligible_product_id_count(ctx) < 2:
        return False
    receipt = ctx.get("receipt_disambiguation")
    if not isinstance(receipt, dict):
        return False
    return str(receipt.get("status") or "").strip() == "no_receipt_evidence"


def is_received_both_indeterminate(ctx: dict[str, Any]) -> bool:
    receipt = ctx.get("receipt_disambiguation")
    if isinstance(receipt, dict):
        status = str(receipt.get("status") or "").strip()
        if status in ("ambiguous_overlap", "no_eligible_receipt_intersection"):
            return True
        rids = receipt.get("receipt_product_ids") or []
        if isinstance(rids, list) and len({int(x) for x in rids if int(x) > 0}) > 1:
            return True
    if ctx.get("fifo_candidate") is True:
        return True
    temporal = ctx.get("temporal_supersession")
    if isinstance(temporal, dict) and temporal.get("fifo_candidate") is True:
        return True
    return False


def is_dsi_running_change_ambiguous_context(ctx: dict[str, Any] | None) -> bool:
    """True when token-level ProductAlias bind must not be the primary steward action."""
    if not ctx or ctx.get("product_match_status") != "ambiguous_eligible":
        return False
    amb = ctx.get("product_ambiguous_eligible")
    if not isinstance(amb, dict):
        return False
    pids = amb.get("product_ids") or []
    if not isinstance(pids, list) or len({int(x) for x in pids if int(x) > 0}) < 2:
        return False
    return is_received_both_indeterminate(ctx) or bool(ctx.get("receipt_disambiguation")) or bool(
        ctx.get("temporal_supersession")
    )


def build_product_resolution_quality(
    stats: dict[str, int],
    *,
    ignored_rows: int = 0,
) -> dict[str, int]:
    total = int(stats.get("total_rows") or 0)
    ignored = max(0, int(ignored_rows))
    unresolved = int(stats.get("unresolved_rows") or 0)
    indeterminate = max(0, unresolved - ignored)
    denominator = max(0, total - ignored)
    return {
        "total_rows": total,
        "resolved_receipt_temporal": int(stats.get("resolved_receipt_temporal") or 0),
        "resolved_other": int(stats.get("resolved_other") or 0),
        "unresolved_rows": unresolved,
        "ignored_rows": ignored,
        "indeterminate_rows": indeterminate,
        "quality_denominator": denominator,
    }


def format_running_change_match_summary(quality: dict[str, int], *, received_both: bool) -> str:
    total = int(quality.get("total_rows") or 0)
    resolved_rt = int(quality.get("resolved_receipt_temporal") or 0)
    indeterminate = int(quality.get("indeterminate_rows") or 0)
    suffix = " (received-both)" if received_both and indeterminate > 0 else ""
    return (
        f"{resolved_rt} of {total} resolved by shipment receipt/temporal; "
        f"{indeterminate} indeterminate{suffix}"
    )


def enrich_product_candidate_running_change_context(
    ctx: dict[str, Any],
    stats: dict[str, int],
    *,
    ignored_rows: int = 0,
) -> None:
    quality = build_product_resolution_quality(stats, ignored_rows=ignored_rows)
    ctx["product_resolution_quality"] = quality
    received_both = is_received_both_indeterminate(ctx)
    ctx["product_running_change_received_both"] = received_both
    if int(quality.get("total_rows") or 0) > 0:
        ctx["product_match_summary"] = format_running_change_match_summary(quality, received_both=received_both)


def infer_dsi_ignore_reason_code(cand_context: dict[str, Any] | None) -> str | None:
    if not cand_context:
        return None
    pstatus = cand_context.get("product_match_status")
    if pstatus == "no_match":
        return IGNORE_REASON_NO_CATALOGUE
    if pstatus == "ambiguous_eligible" and is_received_both_indeterminate(cand_context):
        return IGNORE_REASON_SKU_INDETERMINATE
    if pstatus == "ambiguous_eligible" and is_no_receipt_evidence_ambiguous(cand_context):
        return IGNORE_REASON_NO_RECEIPT_EVIDENCE
    if pstatus == "ambiguous_eligible" and is_dsi_running_change_ambiguous_context(cand_context):
        return IGNORE_REASON_SKU_INDETERMINATE
    return None


AUTO_EXCLUDABLE_PRODUCT_ERROR_CODES = frozenset(
    {
        "unresolved_product",
        "ambiguous_product_match",
        "ambiguous_product_alias",
    }
)

# Product errors that remain hard-blocked (genuine data / governance — not auto-excluded).
PRODUCT_HARD_BLOCK_ERROR_CODES = frozenset(
    {
        "missing_product_token",
        "unresolved_product_inactive_only",
    }
)


def build_validate_line_product_context(perr: str | None, pev: Any) -> dict[str, Any]:
    """Minimal candidate-shaped context for per-line ignore reason inference at validate."""
    ctx: dict[str, Any] = {}
    if perr == "unresolved_product":
        ctx["product_match_status"] = "no_match"
        return ctx
    if perr not in ("ambiguous_product_match", "ambiguous_product_alias"):
        return ctx
    ctx["product_match_status"] = "ambiguous_eligible"
    if pev is None:
        return ctx
    amb = getattr(pev, "ambiguous_eligible", None)
    if isinstance(amb, dict):
        ctx["product_ambiguous_eligible"] = amb
    receipt = getattr(pev, "receipt_disambiguation", None)
    if isinstance(receipt, dict):
        ctx["receipt_disambiguation"] = receipt
    temporal = getattr(pev, "temporal_supersession", None)
    if isinstance(temporal, dict):
        ctx["temporal_supersession"] = temporal
        if temporal.get("fifo_candidate") is True:
            ctx["fifo_candidate"] = True
    return ctx


def infer_validate_auto_exclude_product_reason(perr: str | None, pev: Any) -> str | None:
    """Map a product resolution error + line evidence to a steward ignore reason code."""
    if not perr or perr not in AUTO_EXCLUDABLE_PRODUCT_ERROR_CODES:
        return None
    reason = infer_dsi_ignore_reason_code(build_validate_line_product_context(perr, pev))
    if reason:
        return reason
    if perr in ("ambiguous_product_match", "ambiguous_product_alias"):
        return IGNORE_REASON_SKU_INDETERMINATE
    if perr == "unresolved_product":
        return IGNORE_REASON_NO_CATALOGUE
    return None


def apply_product_auto_exclude_diagnostic(diag: list[str], reason_code: str) -> None:
    tag = steward_ignored_line_diagnostic(reason_code)
    if tag not in diag:
        diag.append(tag)


def compute_dsi_hard_row_with_product_auto_exclude(
    *,
    derr: str | None,
    rdid: int | None,
    perr: str | None,
    rpid: int | None,
    pev: Any,
    diag: list[str],
) -> tuple[bool, str | None]:
    """Returns (hard_row, auto_exclude_reason). Product catalogue/ambiguity → non-blocking exclude."""
    auto_reason = infer_validate_auto_exclude_product_reason(perr, pev) if rpid is None else None
    if auto_reason:
        apply_product_auto_exclude_diagnostic(diag, auto_reason)
        hard_row = bool(derr and rdid is None)
        return hard_row, auto_reason
    hard_row = bool((derr and rdid is None) or (perr and rpid is None))
    return hard_row, None


def product_auto_exclude_terminal_status() -> tuple[str, str]:
    """Non-blocking terminal status for auto-excluded product lines (matches steward-ignore demotion)."""
    return "info", "staged_only"


def steward_ignored_line_diagnostic(reason_code: str) -> str:
    return f"{STEWARD_IGNORED_LINE_DIAG_PREFIX}{reason_code}"


def parse_steward_ignored_line_reason(diag: list[Any] | None) -> str | None:
    for code in diag or []:
        if isinstance(code, str) and code.startswith(STEWARD_IGNORED_LINE_DIAG_PREFIX):
            tail = code[len(STEWARD_IGNORED_LINE_DIAG_PREFIX) :].strip()
            return tail or None
    return None


def demote_staging_line_for_steward_product_ignore(line: Any, reason_code: str) -> None:
    """Terminal steward ignore — status/severity only; never clears resolved_product_id."""
    if line.resolved_product_id is not None:
        return
    diag = list(line.diagnostic_codes or [])
    sd = steward_ignored_line_diagnostic(reason_code)
    if sd not in diag:
        diag.append(sd)
    line.diagnostic_codes = diag
    line.resolution_status = "staged_only"
    line.severity = "info"


def demote_product_staging_lines_for_ignored_candidate(
    db: Any,
    job_id: int,
    normalized_key: str,
    reason_code: str,
) -> int:
    nk = _norm_key_for_steward_ignore_token(normalized_key or "")
    if not nk:
        return 0
    return batch_demote_steward_ignored_product_staging_lines(db, int(job_id), {nk: reason_code})


def _norm_key_for_steward_ignore_token(token: str) -> str:
    from app.services.imports.distributor_sales_inventory import _norm_key

    return _norm_key(token or "")


def batch_demote_steward_ignored_product_staging_lines(
    db: Any,
    job_id: int,
    token_to_reason: dict[str, str],
) -> int:
    """One staging scan per bulk ignore — demote all ignored product tokens in a single pass."""
    if not token_to_reason:
        return 0
    from sqlalchemy import select

    from app.models.import_distributor_si import ImportDistributorSiStagingLine

    reason_by_token = {
        _norm_key_for_steward_ignore_token(k): str(v).strip()
        for k, v in token_to_reason.items()
        if _norm_key_for_steward_ignore_token(k) and str(v).strip()
    }
    if not reason_by_token:
        return 0

    lines = db.scalars(
        select(ImportDistributorSiStagingLine).where(
            ImportDistributorSiStagingLine.import_job_id == int(job_id),
            ImportDistributorSiStagingLine.resolved_product_id.is_(None),
        )
    ).all()
    n = 0
    for line in lines:
        nk = _norm_key_for_steward_ignore_token(line.raw_product_token or "")
        reason = reason_by_token.get(nk)
        if not reason:
            continue
        demote_staging_line_for_steward_product_ignore(line, reason)
        db.add(line)
        n += 1
    return n


def reapply_dsi_steward_ignored_product_staging_lines(db: Any, job_id: int) -> int:
    """Re-apply steward-ignore terminal status after staging refresh (refresh would re-block)."""
    from sqlalchemy import select

    from app.models.import_distributor_si import ImportEntityMappingCandidate

    cands = db.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == int(job_id),
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status == "ignored",
        )
    ).all()
    token_to_reason: dict[str, str] = {}
    for cand in cands:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        rc = str(ctx.get("steward_ignore_reason_code") or infer_dsi_ignore_reason_code(ctx) or "").strip()
        if not rc:
            continue
        nk = _norm_key_for_steward_ignore_token(cand.normalized_key or "")
        if nk:
            token_to_reason[nk] = rc
    return batch_demote_steward_ignored_product_staging_lines(db, int(job_id), token_to_reason)


def _staging_line_units(line: Any) -> float:
    qs = line.quantity_sold
    if qs is None:
        return 0.0
    try:
        return float(qs)
    except (TypeError, ValueError):
        return 0.0


def _staging_line_value(line: Any) -> float:
    computed = getattr(line, "computed_revenue_amount", None)
    if computed is not None:
        try:
            return float(computed)
        except (TypeError, ValueError):
            pass
    reported = getattr(line, "reported_revenue_amount", None)
    if reported is not None:
        try:
            return float(reported)
        except (TypeError, ValueError):
            pass
    return 0.0


def _line_qualifies_for_dsi_fact_write(line: Any) -> bool:
    if parse_steward_ignored_line_reason(
        line.diagnostic_codes if isinstance(line.diagnostic_codes, list) else None
    ):
        return False
    if line.resolved_product_id is None:
        return False
    if not line.resolved_distributor_id:
        return False
    tx = line.transaction_date
    qs = line.quantity_sold
    qty_f = float(qs) if qs is not None else None
    snap = getattr(line, "snapshot_date", None)
    soh = getattr(line, "stock_on_hand", None)
    sellout = (
        tx is not None
        and qty_f is not None
        and qty_f != 0
        and bool(line.resolved_customer_id)
    )
    inv = snap is not None and soh is not None
    return bool(sellout or inv)


def _classify_excluded_line_reason(
    line: Any,
    ignored_token_reasons: dict[str, str],
) -> str:
    diag = line.diagnostic_codes if isinstance(line.diagnostic_codes, list) else []
    steward_rc = parse_steward_ignored_line_reason(diag)
    if steward_rc:
        return steward_rc
    from app.services.imports.distributor_sales_inventory import _norm_key

    token = _norm_key(line.raw_product_token or "")
    if token and token in ignored_token_reasons:
        return ignored_token_reasons[token]
    codes = [str(c) for c in diag]
    if "unresolved_product" in codes:
        return IGNORE_REASON_NO_CATALOGUE
    if "ambiguous_product_match" in codes:
        return IGNORE_REASON_SKU_INDETERMINATE
    return IGNORE_REASON_NO_CATALOGUE


def build_dsi_apply_exclusion_summary(db: Any, job_id: int, lines: list[Any]) -> dict[str, Any]:
    """Reporting-only: applied vs product-excluded volume split by steward ignore reason."""
    from sqlalchemy import select

    from app.models.import_distributor_si import ImportEntityMappingCandidate

    ignored_token_reasons: dict[str, str] = {}
    cands = db.scalars(
        select(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == int(job_id),
            ImportEntityMappingCandidate.entity_type == "product_identifier",
            ImportEntityMappingCandidate.status == "ignored",
        )
    ).all()
    for cand in cands:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        rc = str(ctx.get("steward_ignore_reason_code") or infer_dsi_ignore_reason_code(ctx) or "").strip()
        if rc and cand.normalized_key:
            ignored_token_reasons[str(cand.normalized_key).strip().lower()] = rc

    applied_lines = 0
    applied_units = 0.0
    applied_value = 0.0
    excluded_lines = 0
    excluded_units = 0.0
    excluded_value = 0.0
    by_reason: dict[str, dict[str, float | int]] = {
        IGNORE_REASON_NO_CATALOGUE: {"line_count": 0, "units": 0.0, "value": 0.0},
        IGNORE_REASON_SKU_INDETERMINATE: {"line_count": 0, "units": 0.0, "value": 0.0},
        IGNORE_REASON_NO_RECEIPT_EVIDENCE: {"line_count": 0, "units": 0.0, "value": 0.0},
    }

    for line in lines:
        units = abs(_staging_line_units(line))
        value = abs(_staging_line_value(line))
        if _line_qualifies_for_dsi_fact_write(line):
            applied_lines += 1
            applied_units += units
            applied_value += value
            continue
        if line.resolved_product_id is not None:
            continue
        excluded_lines += 1
        excluded_units += units
        excluded_value += value
        reason = _classify_excluded_line_reason(line, ignored_token_reasons)
        bucket = by_reason.get(reason)
        if bucket is None:
            bucket = {"line_count": 0, "units": 0.0, "value": 0.0}
            by_reason[reason] = bucket
        bucket["line_count"] = int(bucket["line_count"]) + 1
        bucket["units"] = float(bucket["units"]) + units
        bucket["value"] = float(bucket["value"]) + value

    return {
        "applied_line_count": applied_lines,
        "applied_units": round(applied_units, 4),
        "applied_value": round(applied_value, 4),
        "excluded_line_count": excluded_lines,
        "excluded_units": round(excluded_units, 4),
        "excluded_value": round(excluded_value, 4),
        "excluded_by_reason": {
            k: {
                "line_count": int(v["line_count"]),
                "units": round(float(v["units"]), 4),
                "value": round(float(v["value"]), 4),
            }
            for k, v in by_reason.items()
            if int(v["line_count"]) > 0
        },
    }


def build_steward_ignore_remap_context(cand_context: dict[str, Any] | None) -> dict[str, Any]:
    """Preserve enough validation context to reverse ignore → needs_review later."""
    if not cand_context:
        return {}
    keys = (
        "product_match_status",
        "product_ambiguous_eligible",
        "product_inactive_matches",
        "receipt_disambiguation",
        "temporal_supersession",
        "fifo_candidate",
        "product_resolution_quality",
        "product_running_change_received_both",
        "dominant_unresolved_distributor_id",
        "dominant_evidence_month",
        "shipment_distinct_product_ids",
        "dsi_evidence_month_counts",
        "shipment_evidence_month_counts",
    )
    out: dict[str, Any] = {}
    for k in keys:
        if k in cand_context and cand_context[k] is not None:
            out[k] = cand_context[k]
    return out
