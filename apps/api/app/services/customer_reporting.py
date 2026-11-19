"""The one definition of a reporting customer.

The app-wide flag is ``customer_report_config.reports_expected``: the CST steward switch
"Key accounts & feed profile" > "Reports expected". A reporting customer is that flag true AND not
merged into another customer. Every reader of the flag uses these helpers, so a customer is
reporting everywhere or nowhere: the CST upload picker (``cst_layouts.list_reporting_customers``),
the CST due/late/missing slot job (``cst_d1.advance_cst_report_slots``), the ops report health
figures, the line-up reporting gate, the new-customer proposal check and picker, listing discovery,
listing autoconfig, listing coverage, site onboarding, stock-not-listed and the sell-through
overview. Only the CST steward editor reads and writes the raw flag (it is the switch itself).

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Select, and_, select

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer

# Where a steward sets the flag; shown in every refusal so the fix is findable.
WHERE_THE_FLAG_IS_SET = "CST steward > Key accounts & feed profile > Reports expected"


def reporting_customer_clauses() -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """WHERE clauses of the definition (the query must join ``customer_report_config``)."""
    return (
        CustomerReportConfig.reports_expected.is_(True),
        DimCustomer.merged_into_customer_id.is_(None),
    )


def reporting_customer_expr() -> ColumnElement[bool]:
    """The definition as one boolean expression, for a SELECT list or an ``or_`` with other rules.

    Over an outer join a customer with no config row reads NULL (not reporting).
    """
    return and_(*reporting_customer_clauses())


def reporting_customer_ids_select() -> Select[tuple[int]]:
    """``SELECT dim_customer.id`` of every reporting customer."""
    return (
        select(DimCustomer.id)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(*reporting_customer_clauses())
    )


def is_reporting(config: Any, customer: Any) -> bool:
    """The definition for rows already loaded: the flag is true and the customer is not merged away.

    A missing config row or a missing customer is not reporting.
    """
    if config is None or customer is None:
        return False
    return bool(getattr(config, "reports_expected", False)) and (
        getattr(customer, "merged_into_customer_id", None) is None
    )
