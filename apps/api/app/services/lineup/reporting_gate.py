"""One reporting-only rule for every path that writes customer line-up rows from a file.

Warren 2026-11-19: the line-up upload/import paths refuse rows for customers that are not reporting
(``customer_report_config.reports_expected`` true), the same meaning as listing discovery, the CST
upload, the new-customer proposal and the automatic per-customer pull. The set of reporting
customers comes from ``customer_reporting`` (the single definition: reports expected, not merged).

Refused rows are reported back with a reason; they are never dropped silently. A row whose customer
could not be resolved at all is not a customer row and keeps its existing handling (an
``unknown_customer`` diagnostic on the file parser).

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer
from app.models.lineup import FactLineupPlanItem
from app.services.customer_reporting import WHERE_THE_FLAG_IS_SET, reporting_customer_ids_select


def reporting_plan_items_clause() -> ColumnElement[bool]:
    """WHERE clause for READS of ``fact_lineup_plan_item``: the row's customer is reporting.

    Line-ups exist only for reporting customers, so every list, count and planned-reservation read
    carries this. The definition is the shared one (``reporting_customer_ids_select``: reports
    expected true and not merged away); nothing here re-implements it.
    """
    return FactLineupPlanItem.customer_id.in_(reporting_customer_ids_select())


REASON_NOT_REPORTING = "customer_not_reporting"
REFUSAL_MESSAGE = (
    "This customer is not reporting (reports expected is off), so line-up rows are not "
    "accepted for it. Mark the customer as reporting first "
    f"({WHERE_THE_FLAG_IS_SET})."
)


def not_reporting_detail() -> dict[str, str]:
    """The structured refusal a line-up WRITE endpoint returns for a non-reporting customer."""
    return {"code": REASON_NOT_REPORTING, "message": REFUSAL_MESSAGE}


async def customer_is_reporting(db: AsyncSession, customer_id: int | None) -> bool:
    """True when ``customer_id`` is a reporting customer (the shared definition).

    A missing customer id is not reporting. Used by the line-up write endpoints so a write never
    acts on a customer the read paths hide.
    """
    if customer_id is None:
        return False
    found = await db.execute(
        reporting_customer_ids_select().where(DimCustomer.id == int(customer_id)).limit(1)
    )
    return found.scalars().first() is not None
# The count is always exact; only the listed rows are capped (keeps job results small).
MAX_REFUSED_ROWS_REPORTED = 200


def refused_row(row: dict[str, Any]) -> dict[str, Any]:
    """The refusal record for one parsed file row."""
    return {
        "source_row_number": row.get("source_row_number"),
        "customer_id": row.get("customer_id"),
        "customer_token": row.get("customer_token"),
        "sku_raw": row.get("sku_raw"),
        "reason": REASON_NOT_REPORTING,
        "message": REFUSAL_MESSAGE,
    }


def split_rows_by_reporting(
    rows: Iterable[dict[str, Any]], reporting_ids: set[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(kept, refused)``: refuses only rows whose resolved ``customer_id`` is not reporting."""
    kept: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for row in rows:
        customer_id = row.get("customer_id")
        if customer_id is not None and int(customer_id) not in reporting_ids:
            refused.append(refused_row(row))
        else:
            kept.append(row)
    return kept, refused


def cap_refused_rows(refused: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return refused[:MAX_REFUSED_ROWS_REPORTED]


def refusal_warning(count: int) -> str:
    return f"{count} row(s) refused: customer is not reporting (reports expected is off)."
