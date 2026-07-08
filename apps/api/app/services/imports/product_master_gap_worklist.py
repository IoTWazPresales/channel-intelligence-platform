"""Cross-import unresolved product token worklist (derived-on-read).

Aggregates shipment evidence, DSI mapping candidates, and other product-resolving
importers into one steward-facing vocabulary gap surface. No new tables; no auto-create.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.shipment_evidence_current import ShipmentEvidenceCurrent
from app.services.imports.dsi_product_running_change import (
    STEWARD_IGNORED_LINE_DIAG_PREFIX,
    infer_dsi_ignore_reason_code,
)

SourceKind = Literal["shipment", "dsi"]
WorklistStatus = Literal["unresolved", "ignored"]

_SHIPMENT_UNRESOLVED_STATUSES = frozenset({"no_match", "inactive_only", "ambiguous", "no_identifier"})


def _norm_token(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().upper())


def _shipment_display_token(row: ShipmentEvidenceCurrent) -> str:
    for field in (
        row.product_resolution_token,
        row.item_code,
        row.ean_code,
        row.upc_code,
        row.sales_model_name,
        row.customer_item,
        row.mpor_item_no,
    ):
        t = _norm_token(field)
        if t:
            return t
    return ""


async def product_master_gap_worklist(
    db: AsyncSession,
    *,
    source: SourceKind | None = None,
    status: WorklistStatus | None = None,
    search: str | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    """Return unresolved/ignored product tokens grouped by normalized token."""
    rows_by_token: dict[str, dict[str, Any]] = {}

    if source in (None, "shipment"):
        await _merge_shipment_tokens(db, rows_by_token)
    if source in (None, "dsi"):
        await _merge_dsi_tokens(db, rows_by_token)

    out = sorted(rows_by_token.values(), key=lambda r: (-int(r["occurrence_count"]), r["token"]))
    if status:
        out = [r for r in out if r["status"] == status]
    if search:
        q = search.strip().upper()
        out = [r for r in out if q in r["token"] or q in (r.get("sample_identifiers") or "").upper()]

    truncated = len(out) > limit
    out = out[:limit]

    return {
        "rows": out,
        "total": len(out),
        "truncated": truncated,
        "status_vocabulary": {
            "shipment": sorted(_SHIPMENT_UNRESOLVED_STATUSES),
            "dsi": ["needs_review", "ignored", "resolved"],
            "worklist": ["unresolved", "ignored"],
        },
        "data_unavailable": False,
    }


async def _merge_shipment_tokens(db: AsyncSession, rows_by_token: dict[str, dict[str, Any]]) -> None:
    agg = (
        await db.execute(
            select(
                ShipmentEvidenceCurrent.product_resolution_token,
                ShipmentEvidenceCurrent.product_resolution_status,
                ShipmentEvidenceCurrent.item_code,
                ShipmentEvidenceCurrent.ean_code,
                ShipmentEvidenceCurrent.upc_code,
                ShipmentEvidenceCurrent.sales_model_name,
                func.count().label("n"),
                func.coalesce(func.sum(ShipmentEvidenceCurrent.quantity), 0).label("qty"),
                func.min(ShipmentEvidenceCurrent.import_job_id).label("first_job"),
                func.max(ShipmentEvidenceCurrent.import_job_id).label("last_job"),
                func.min(ShipmentEvidenceCurrent.observed_at).label("first_seen"),
                func.max(ShipmentEvidenceCurrent.observed_at).label("last_seen"),
            )
            .where(
                ShipmentEvidenceCurrent.product_id.is_(None),
                ShipmentEvidenceCurrent.product_resolution_status.in_(tuple(_SHIPMENT_UNRESOLVED_STATUSES)),
            )
            .group_by(
                ShipmentEvidenceCurrent.product_resolution_token,
                ShipmentEvidenceCurrent.product_resolution_status,
                ShipmentEvidenceCurrent.item_code,
                ShipmentEvidenceCurrent.ean_code,
                ShipmentEvidenceCurrent.upc_code,
                ShipmentEvidenceCurrent.sales_model_name,
            )
        )
    ).all()

    for row in agg:
        # Build a synthetic row for token extraction
        class _R:
            pass

        r = _R()
        r.product_resolution_token = row.product_resolution_token
        r.item_code = row.item_code
        r.ean_code = row.ean_code
        r.upc_code = row.upc_code
        r.sales_model_name = row.sales_model_name
        r.customer_item = None
        r.mpor_item_no = None
        token = _shipment_display_token(r)
        if not token:
            token = _norm_token(row.product_resolution_token) or "UNKNOWN"
        _upsert_token_row(
            rows_by_token,
            token=token,
            source="shipment",
            status="unresolved",
            resolution_status=str(row.product_resolution_status),
            occurrence_count=int(row.n),
            quantity_impact=float(row.qty or 0),
            sample_identifiers=_sample_ids(row.item_code, row.ean_code, row.sales_model_name),
            job_ids={int(row.first_job), int(row.last_job)},
            first_seen=row.first_seen,
            last_seen=row.last_seen,
        )


async def _merge_dsi_tokens(db: AsyncSession, rows_by_token: dict[str, dict[str, Any]]) -> None:
    candidates = (
        await db.execute(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.entity_type == "product_identifier",
                ImportEntityMappingCandidate.status.in_(("needs_review", "ignored")),
            )
        )
    ).scalars().all()

    for cand in candidates:
        token = _norm_token(cand.normalized_key)
        if not token:
            continue
        ctx = cand.context if isinstance(cand.context, dict) else {}
        ignored_reason = None
        if cand.status == "ignored":
            ignored_reason = str(ctx.get("steward_ignore_reason_code") or infer_dsi_ignore_reason_code(ctx) or "ignored")
        for code in ctx.get("diagnostic_codes") or []:
            if isinstance(code, str) and code.startswith(STEWARD_IGNORED_LINE_DIAG_PREFIX):
                ignored_reason = code[len(STEWARD_IGNORED_LINE_DIAG_PREFIX) :].strip() or ignored_reason

        wl_status: WorklistStatus = "ignored" if cand.status == "ignored" or ignored_reason else "unresolved"
        pstatus = str(ctx.get("product_match_status") or cand.match_reason or "needs_review")
        sample = cand.sample_raw_values[0] if isinstance(cand.sample_raw_values, list) and cand.sample_raw_values else None
        _upsert_token_row(
            rows_by_token,
            token=token,
            source="dsi",
            status=wl_status,
            resolution_status=pstatus if wl_status == "unresolved" else (ignored_reason or "ignored"),
            occurrence_count=int(cand.row_count or 0),
            quantity_impact=float(cand.total_units or 0),
            sample_identifiers=str(sample) if sample else token,
            job_ids={int(cand.import_job_id)},
            first_seen=cand.created_at,
            last_seen=cand.updated_at or cand.created_at,
        )


def _sample_ids(item: str | None, ean: str | None, model: str | None) -> str:
    parts = [p for p in (item, ean, model) if p and str(p).strip()]
    return " · ".join(parts[:3])


def _upsert_token_row(
    rows_by_token: dict[str, dict[str, Any]],
    *,
    token: str,
    source: str,
    status: WorklistStatus,
    resolution_status: str,
    occurrence_count: int,
    quantity_impact: float,
    sample_identifiers: str,
    job_ids: set[int],
    first_seen: datetime | None,
    last_seen: datetime | None,
) -> None:
    key = token
    existing = rows_by_token.get(key)
    if existing is None:
        rows_by_token[key] = {
            "token": token,
            "sources": [source],
            "status": status,
            "resolution_statuses": [resolution_status],
            "occurrence_count": occurrence_count,
            "quantity_impact": quantity_impact,
            "sample_identifiers": sample_identifiers,
            "first_seen": first_seen.isoformat() if first_seen else None,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "affected_job_ids": sorted(job_ids),
            "deep_link": _deep_link(source, job_ids),
        }
        return

    if source not in existing["sources"]:
        existing["sources"].append(source)
    if resolution_status not in existing["resolution_statuses"]:
        existing["resolution_statuses"].append(resolution_status)
    # ignored wins visibility when either source is ignored
    if status == "ignored":
        existing["status"] = "ignored"
    existing["occurrence_count"] += occurrence_count
    existing["quantity_impact"] += quantity_impact
    merged_jobs = set(existing["affected_job_ids"]) | job_ids
    existing["affected_job_ids"] = sorted(merged_jobs)
    existing["deep_link"] = _deep_link(existing["sources"][0], merged_jobs)
    if first_seen and (not existing["first_seen"] or first_seen.isoformat() < existing["first_seen"]):
        existing["first_seen"] = first_seen.isoformat()
    if last_seen and (not existing["last_seen"] or last_seen.isoformat() > existing["last_seen"]):
        existing["last_seen"] = last_seen.isoformat()


def _deep_link(source: str, job_ids: set[int]) -> dict[str, str]:
    jid = min(job_ids) if job_ids else None
    if source == "dsi" and jid is not None:
        return {
            "href": f"/admin/imports?job={jid}&entity=product",
            "label": "DSI steward",
        }
    if source == "shipment" and jid is not None:
        return {
            "href": f"/admin/shipment-evidence?job_id={jid}&entity=product",
            "label": "Shipment steward",
        }
    return {"href": "/admin/imports", "label": "Import center"}
