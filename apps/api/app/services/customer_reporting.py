"""The one definition of a reporting customer.

The app-wide flag is ``customer_report_config.reports_expected``: the CST steward switch
"Key accounts & feed profile" > "Reports expected". A reporting customer is that flag true AND not
merged into another customer. The CST upload picker (``cst_layouts.list_reporting_customers``), the
line-up reporting gate, the new-customer proposal check and the new-customer picker all use these
helpers, so a customer is reporting everywhere or nowhere.

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, Select, select

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


def reporting_customer_ids_select() -> Select[tuple[int]]:
    """``SELECT dim_customer.id`` of every reporting customer."""
    return (
        select(DimCustomer.id)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(*reporting_customer_clauses())
    )
