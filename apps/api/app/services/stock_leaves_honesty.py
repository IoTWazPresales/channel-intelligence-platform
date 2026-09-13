"""Read-only ThinLens grains for Stock Sell-through and Forecasts.

Callers must print current_database() first. ISO weeks are Monday-keyed in
Africa/Johannesburg, same as Movement. Do not copy lab fixture W36 / TechMart.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user

logger = logging.getLogger(__name__)

TRAILING_WEEKS = 8

_BOUNDS_SQL = """
WITH bounds AS (
  SELECT
    (now() AT TIME ZONE 'Africa/Johannesburg')::date AS today_sast,
    (
      (now() AT TIME ZONE 'Africa/Johannesburg')::date
      - (EXTRACT(ISODOW FROM (now() AT TIME ZONE 'Africa/Johannesburg')::date)::int - 1)
    )::date AS week_monday
)
SELECT
  current_database() AS database,
  b.today_sast,
  to_char(b.today_sast, 'IYYY-"W"IW') AS current_iso_week,
  (
    SELECT count(*)::int
    FROM fact_customer_sellthrough s
    WHERE s.tenant_id = :tenant
      AND s.period_start_date >= b.week_monday
      AND s.period_start_date < b.week_monday + 7
  ) AS cst_current_week_rows,
  (
    SELECT max(s.period_start_date)
    FROM fact_customer_sellthrough s
    WHERE s.tenant_id = :tenant
  ) AS cst_max_period,
  (
    SELECT to_char(max(s.period_start_date), 'IYYY-"W"IW')
    FROM fact_customer_sellthrough s
    WHERE s.tenant_id = :tenant
  ) AS cst_max_iso_week,
  (
    SELECT count(*)::int
    FROM fact_customer_sellthrough s
    WHERE s.tenant_id = :tenant
      AND s.period_start_date = (
        SELECT max(s2.period_start_date) FROM fact_customer_sellthrough s2 WHERE s2.tenant_id = :tenant
      )
  ) AS cst_max_period_rows,
  (
    SELECT count(*)::int FROM (
      SELECT DISTINCT (
        so.transaction_date - (EXTRACT(ISODOW FROM so.transaction_date)::int - 1)
      ) AS week_monday
      FROM fact_sales_sellout so
      WHERE so.tenant_id = :tenant
        AND so.transaction_date >= b.week_monday - 49
        AND so.transaction_date < b.week_monday + 7
    ) w
  ) AS sellout_trailing_weeks,
  (
    SELECT max(so.transaction_date)
    FROM fact_sales_sellout so
    WHERE so.tenant_id = :tenant
  ) AS sellout_max_tx,
  (
    SELECT to_char(max(so.transaction_date), 'IYYY-"W"IW')
    FROM fact_sales_sellout so
    WHERE so.tenant_id = :tenant
  ) AS sellout_max_iso_week,
  (
    SELECT count(*)::int
    FROM fact_demand_forecast f
    WHERE f.tenant_id = :tenant
  ) AS forecast_rows
FROM bounds b
"""

_CUSTOMERS_SQL = """
SELECT c.name AS name, count(*)::int AS n
FROM fact_customer_sellthrough s
JOIN dim_customer c ON c.id = s.customer_id
WHERE s.tenant_id = :tenant
  AND s.period_start_date = (
    SELECT max(s2.period_start_date) FROM fact_customer_sellthrough s2 WHERE s2.tenant_id = :tenant
  )
GROUP BY c.name
ORDER BY n DESC
LIMIT 3
"""


def week_short(iso_week: str | None) -> str:
    """'2026-W37' → 'W37'."""
    if not iso_week:
        return "—"
    if "-W" in iso_week:
        return "W" + iso_week.split("-W", 1)[1]
    return iso_week


def sellthrough_title(*, current_week: str, current_week_rows: int) -> str:
    if current_week_rows <= 0:
        return f"Retailer sell-through for {current_week} not yet imported"
    return f"Retailer sell-through applied in {current_week}"


def forecast_title(*, trailing_weeks: int) -> str:
    if trailing_weeks < TRAILING_WEEKS:
        return "Forecasts need 8 weeks of applied sell-out"
    return "Forecast trailing window is complete"


def _empty(dbname: str | None, tenant: str) -> dict[str, Any]:
    return {
        "database": dbname,
        "tenant_id": tenant,
        "data_unavailable": True,
        "sellthrough": {},
        "forecast": {},
    }


async def stock_leaves_honesty(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    dbname = await db.scalar(text("SELECT current_database()"))
    tenant = tenant_id_from_user(user)
    try:
        row = (await db.execute(text(_BOUNDS_SQL), {"tenant": tenant})).mappings().one()
        customers = [
            dict(r)
            for r in (await db.execute(text(_CUSTOMERS_SQL), {"tenant": tenant})).mappings().all()
        ]
    except Exception:
        logger.exception("stock_leaves_honesty query failed")
        return _empty(str(dbname) if dbname is not None else None, tenant)

    current_iso = str(row["current_iso_week"] or "")
    current_short = week_short(current_iso)
    cst_now = int(row["cst_current_week_rows"] or 0)
    cst_max_iso = row["cst_max_iso_week"]
    cst_max_short = week_short(str(cst_max_iso) if cst_max_iso else None)
    cst_max_rows = int(row["cst_max_period_rows"] or 0)
    cst_max_period = row["cst_max_period"]
    trailing = int(row["sellout_trailing_weeks"] or 0)
    so_max_iso = row["sellout_max_iso_week"]
    so_max_short = week_short(str(so_max_iso) if so_max_iso else None)
    so_max_tx = row["sellout_max_tx"]
    forecast_n = int(row["forecast_rows"] or 0)
    customer_names = [str(c["name"]) for c in customers if c.get("name")]

    cst_body_parts = [
        "Sell-through is derived from retailer files (fact_customer_sellthrough.period_start_date, ISO week in Africa/Johannesburg).",
        f"Current ISO week {current_short} has {cst_now} rows.",
    ]
    if cst_max_period is not None:
        cst_body_parts.append(
            f"Latest applied period_start is {cst_max_period.isoformat()} ({cst_max_short}, {cst_max_rows} rows)"
            + (f" — {', '.join(customer_names)}" if customer_names else "")
            + "."
        )
    else:
        cst_body_parts.append("No fact_customer_sellthrough rows.")
    cst_body_parts.append("Not lab fixture W36 / TechMart.")

    fc_body = (
        f"Trailing window is the current ISO Monday plus seven prior Mondays ({TRAILING_WEEKS} weeks). "
        f"fact_sales_sellout.transaction_date has {trailing} of {TRAILING_WEEKS} weeks. "
        + (
            f"Latest sell-out is {so_max_short} ({so_max_tx.isoformat()}). "
            if so_max_tx is not None
            else "No fact_sales_sellout rows. "
        )
        + f"{forecast_n} fact_demand_forecast rows stay on the relocated workspace — they are not a complete trailing window. "
        "Velocity and analogue projections are labelled by method."
    )

    return {
        "database": row["database"] or dbname,
        "tenant_id": tenant,
        "data_unavailable": False,
        "today_sast": row["today_sast"].isoformat() if row["today_sast"] is not None else None,
        "sellthrough": {
            "current_iso_week": current_iso,
            "current_week_label": current_short,
            "current_week_rows": cst_now,
            "latest_iso_week": cst_max_iso,
            "latest_week_label": cst_max_short,
            "latest_period_start": cst_max_period.isoformat() if cst_max_period is not None else None,
            "latest_period_rows": cst_max_rows,
            "latest_customers": customer_names,
            "title": sellthrough_title(current_week=current_short, current_week_rows=cst_now),
            "body": " ".join(cst_body_parts),
            "window_complete": cst_now > 0,
        },
        "forecast": {
            "trailing_weeks": trailing,
            "trailing_needed": TRAILING_WEEKS,
            "latest_iso_week": so_max_iso,
            "latest_week_label": so_max_short,
            "latest_transaction_date": so_max_tx.isoformat() if so_max_tx is not None else None,
            "forecast_rows": forecast_n,
            "title": forecast_title(trailing_weeks=trailing),
            "body": fc_body,
            "window_complete": trailing >= TRAILING_WEEKS,
        },
        "number_class": {
            "cst_current_week_rows": "iii",
            "sellout_trailing_weeks": "iii",
            "forecast_rows": "iii",
        },
    }
