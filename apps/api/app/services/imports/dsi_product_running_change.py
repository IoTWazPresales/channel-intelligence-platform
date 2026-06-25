"""Display + steward disposition helpers for DSI running-change / supersession product tokens.

Does not alter resolver tier order or receipt/temporal logic — stats, summaries, and ignore reason codes only.
"""

from __future__ import annotations

from typing import Any

IGNORE_REASON_SKU_INDETERMINATE = "ignore_sku_indeterminate"
IGNORE_REASON_NO_CATALOGUE = "ignore_no_catalogue"

DSI_IGNORE_REASON_CODES = frozenset({IGNORE_REASON_SKU_INDETERMINATE, IGNORE_REASON_NO_CATALOGUE})

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
    if pstatus == "ambiguous_eligible" and is_dsi_running_change_ambiguous_context(cand_context):
        return IGNORE_REASON_SKU_INDETERMINATE
    return None


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
