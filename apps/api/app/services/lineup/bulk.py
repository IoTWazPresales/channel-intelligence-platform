"""Bulk upsert for fact_lineup_plan_item with row-level outcomes (no silent overwrites)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem

_LINEUP_APPROVAL = frozenset(
    {"draft", "pending_approval", "submitted", "approved", "rejected"},
)


def _parse_bool(v: Any) -> bool:
    if v is None or v is False:
        return False
    if v is True:
        return True
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _parse_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def dedupe_lineup_input_rows(rows: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    """Later rows win the same natural key (customer_code, channel_code, period_start, sku)."""
    key_to_last: dict[tuple[str, str, str, str], tuple[int, dict[str, Any]]] = {}
    for i, r in enumerate(rows):
        cc = str(r.get("customer_code") or "").strip()
        ch = str(r.get("channel_code") or "").strip()
        ps = str(r.get("period_start") or "").strip()
        sku = str(r.get("sku") or "").strip()
        key = (cc.lower(), ch.lower(), ps, sku.lower())
        key_to_last[key] = (i, r)
    return sorted(key_to_last.values(), key=lambda t: t[0])


async def _find_existing(
    db: AsyncSession,
    *,
    customer_id: int,
    channel_id: int | None,
    period_start: date,
    product_id: int,
) -> FactLineupPlanItem | None:
    parts = [
        FactLineupPlanItem.customer_id == customer_id,
        FactLineupPlanItem.period_start == period_start,
        FactLineupPlanItem.product_id == product_id,
    ]
    if channel_id is None:
        parts.append(FactLineupPlanItem.channel_id.is_(None))
    else:
        parts.append(FactLineupPlanItem.channel_id == channel_id)
    res = await db.execute(select(FactLineupPlanItem).where(and_(*parts)).limit(1))
    return res.scalar_one_or_none()


async def bulk_upsert_lineup_items(
    db: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    replace_matching: bool,
) -> dict[str, Any]:
    if len(rows) > 2000:
        raise ValueError("Too many rows (max 2000)")

    cust_res = await db.execute(select(DimCustomer))
    customers = {c.code.strip().lower(): c for c in cust_res.scalars().all()}

    ch_res = await db.execute(select(DimChannel))
    channels = {c.code.strip().lower(): c for c in ch_res.scalars().all()}

    prod_res = await db.execute(select(DimProduct))
    products_by_sku = {p.sku.strip().lower(): p for p in prod_res.scalars().all()}

    results: list[dict[str, Any]] = []
    inserted = updated = skipped = 0

    for row_index, raw in dedupe_lineup_input_rows(rows):
        errs: list[str] = []
        cc = str(raw.get("customer_code") or "").strip()
        sku = str(raw.get("sku") or "").strip()
        ps_raw = raw.get("period_start")
        if not cc:
            errs.append("customer_code is required")
        if not sku:
            errs.append("sku is required")
        if ps_raw is None or str(ps_raw).strip() == "":
            errs.append("period_start is required")
        period_start: date | None = None
        if ps_raw is not None and str(ps_raw).strip():
            try:
                period_start = date.fromisoformat(str(ps_raw).strip()[:10])
            except ValueError:
                errs.append("period_start must be ISO date (YYYY-MM-DD)")
        cust = customers.get(cc.lower()) if cc else None
        if cc and not cust:
            errs.append(f"Unknown customer_code {cc!r}")
        prod = products_by_sku.get(sku.lower()) if sku else None
        if sku and not prod:
            errs.append(f"Unknown sku {sku!r}")

        ch_code = str(raw.get("channel_code") or "").strip()
        channel_id: int | None = None
        if ch_code:
            ch = channels.get(ch_code.lower())
            if not ch:
                errs.append(f"Unknown channel_code {ch_code!r}")
            else:
                channel_id = ch.id

        pred_id: int | None = None
        succ_id: int | None = None
        pred_sku = str(raw.get("predecessor_sku") or "").strip()
        if pred_sku:
            p = products_by_sku.get(pred_sku.lower())
            if not p:
                errs.append(f"Unknown predecessor_sku {pred_sku!r}")
            else:
                pred_id = p.id
        succ_sku = str(raw.get("successor_sku") or "").strip()
        if succ_sku:
            p = products_by_sku.get(succ_sku.lower())
            if not p:
                errs.append(f"Unknown successor_sku {succ_sku!r}")
            else:
                succ_id = p.id

        st_raw = str(raw.get("approval_status") or "draft").strip() or "draft"
        if st_raw not in _LINEUP_APPROVAL:
            errs.append(f"Invalid approval_status {st_raw!r}")
        approval_status = st_raw if not errs else "draft"

        planned_vol = _parse_float(raw.get("planned_volume_units"))
        if planned_vol is None:
            planned_vol = 0.0
        cur_vol = _parse_float(raw.get("current_volume_units"))

        planned_launch: date | None = None
        if raw.get("planned_launch_date"):
            try:
                planned_launch = date.fromisoformat(str(raw.get("planned_launch_date")).strip()[:10])
            except ValueError:
                errs.append("planned_launch_date must be ISO date")
        planned_eol: date | None = None
        if raw.get("planned_eol_date"):
            try:
                planned_eol = date.fromisoformat(str(raw.get("planned_eol_date")).strip()[:10])
            except ValueError:
                errs.append("planned_eol_date must be ISO date")

        if errs:
            results.append({"row_index": row_index, "status": "error", "errors": errs})
            continue

        assert cust is not None and prod is not None and period_start is not None

        existing = await _find_existing(
            db,
            customer_id=cust.id,
            channel_id=channel_id,
            period_start=period_start,
            product_id=prod.id,
        )

        period_label = raw.get("period_label")
        period_label_s = str(period_label).strip() if period_label not in (None, "") else None
        prs = raw.get("planned_range_summary")
        prs_s = str(prs).strip() if prs not in (None, "") else None
        crs = raw.get("current_range_summary")
        crs_s = str(crs).strip() if crs not in (None, "") else None
        notes_raw = raw.get("notes")
        notes_s = str(notes_raw).strip() if notes_raw not in (None, "") else None

        overlap = _parse_bool(raw.get("overlap_cannibalization_flag"))
        whitespace = _parse_bool(raw.get("whitespace_gap_flag"))

        if existing is None:
            row = FactLineupPlanItem(
                customer_id=cust.id,
                channel_id=channel_id,
                period_start=period_start,
                period_label=period_label_s,
                product_id=prod.id,
                predecessor_product_id=pred_id,
                successor_product_id=succ_id,
                current_range_summary=crs_s,
                planned_range_summary=prs_s,
                planned_launch_date=planned_launch,
                planned_eol_date=planned_eol,
                current_volume_units=cur_vol,
                planned_volume_units=planned_vol,
                overlap_cannibalization_flag=overlap,
                whitespace_gap_flag=whitespace,
                approval_status=approval_status,
                notes=notes_s,
            )
            db.add(row)
            await db.flush()
            inserted += 1
            results.append({"row_index": row_index, "status": "inserted", "id": row.id, "errors": []})
            continue

        if not replace_matching:
            skipped += 1
            results.append(
                {
                    "row_index": row_index,
                    "status": "skipped",
                    "id": existing.id,
                    "errors": ["Natural key already exists; pass replace_matching=true to update"],
                }
            )
            continue

        existing.predecessor_product_id = pred_id
        existing.successor_product_id = succ_id
        existing.current_range_summary = crs_s
        existing.planned_range_summary = prs_s
        existing.planned_launch_date = planned_launch
        existing.planned_eol_date = planned_eol
        if cur_vol is not None:
            existing.current_volume_units = cur_vol
        existing.planned_volume_units = planned_vol
        existing.overlap_cannibalization_flag = overlap
        existing.whitespace_gap_flag = whitespace
        existing.approval_status = approval_status
        existing.notes = notes_s
        if period_label_s is not None:
            existing.period_label = period_label_s
        updated += 1
        results.append({"row_index": row_index, "status": "updated", "id": existing.id, "errors": []})

    await db.commit()
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": sum(1 for r in results if r["status"] == "error"),
        "results": results,
    }
