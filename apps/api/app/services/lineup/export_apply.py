"""B2-03 — export + apply helpers for lineup net-requirement."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer, DimProduct
from app.services.lineup.bulk import bulk_upsert_lineup_items
from app.services.lineup.net_requirement import build_net_requirement_rows


def net_requirement_to_csv(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "distributor_id", "product_id", "business_unit", "period_from", "period_to",
        "forecast_demand", "bias_adjusted_forecast", "channel_stock", "in_transit",
        "target_cover_units", "net_requirement", "weekly_velocity", "bias_factor",
    ])
    for r in payload.get("rows") or []:
        writer.writerow([
            r.get("distributor_id"), r.get("product_id"), r.get("business_unit") or "",
            r.get("period_from"), r.get("period_to"), r.get("forecast_demand"),
            r.get("bias_adjusted_forecast"), r.get("channel_stock"), r.get("in_transit"),
            r.get("target_cover_units"), r.get("net_requirement"), r.get("weekly_velocity"),
            r.get("bias_factor"),
        ])
    return buf.getvalue()


def half_year_period_starts(year: int, half: int) -> list[tuple[date, str]]:
    if half not in (1, 2):
        raise ValueError("half must be 1 or 2")
    if half == 1:
        return [(date(year, 1, 1), f"{str(year)[2:]}Q1"), (date(year, 4, 1), f"{str(year)[2:]}Q2")]
    return [(date(year, 7, 1), f"{str(year)[2:]}Q3"), (date(year, 10, 1), f"{str(year)[2:]}Q4")]


async def apply_net_requirement_to_lineup(
    db: AsyncSession,
    *,
    period_start: date,
    period_label: str | None = None,
    distributor_id: int | None = None,
    horizon_weeks: int = 13,
    target_cover_weeks: float = 4.0,
    replace_matching: bool = True,
    limit: int = 200,
) -> dict[str, Any]:
    product_bu: dict[int, str] = {}
    for pid, pl, bu in (
        await db.execute(select(DimProduct.id, DimProduct.product_line, DimProduct.business_unit))
    ).all():
        label = (bu or pl or "").strip()
        if label:
            product_bu[int(pid)] = label

    payload = await build_net_requirement_rows(
        db,
        horizon_weeks=horizon_weeks,
        target_cover_weeks=target_cover_weeks,
        distributor_id=distributor_id,
        product_bu=product_bu,
        include_customer_shares=True,
        limit=limit,
    )

    cust_codes = {int(r.id): str(r.code) for r in (await db.execute(select(DimCustomer))).scalars().all()}
    prod_skus = {int(r.id): str(r.sku) for r in (await db.execute(select(DimProduct))).scalars().all()}

    rows: list[dict[str, Any]] = []
    skipped_zero = 0
    skipped_no_alloc = 0
    for nr in payload.get("rows") or []:
        net = float(nr.get("net_requirement") or 0)
        if net <= 0:
            skipped_zero += 1
            continue
        alloc = nr.get("customer_allocation") or []
        if not alloc:
            skipped_no_alloc += 1
            continue
        pid = int(nr["product_id"])
        sku = prod_skus.get(pid)
        if not sku:
            continue
        for a in alloc:
            cid = int(a["customer_id"])
            code = cust_codes.get(cid)
            if not code:
                continue
            units = float(a.get("suggested_lineup_units") or 0)
            if units <= 0:
                continue
            rows.append({
                "customer_code": code,
                "channel_code": None,
                "period_start": period_start.isoformat(),
                "period_label": period_label,
                "sku": sku,
                "planned_volume_units": units,
                "approval_status": "draft",
                "notes": f"b2_net_requirement dist={nr['distributor_id']} forecast_share={a.get('share')}",
            })

    if not rows:
        return {
            "inserted": 0, "updated": 0, "skipped": 0, "errors": 0, "results": [],
            "skipped_zero_net": skipped_zero, "skipped_no_allocation": skipped_no_alloc,
            "source_row_count": payload.get("row_count", 0), "draft_rows_built": 0,
        }

    out = await bulk_upsert_lineup_items(db, rows, replace_matching=replace_matching)
    out["skipped_zero_net"] = skipped_zero
    out["skipped_no_allocation"] = skipped_no_alloc
    out["source_row_count"] = payload.get("row_count", 0)
    out["draft_rows_built"] = len(rows)
    return out
