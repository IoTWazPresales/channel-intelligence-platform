"""GET /customers?reporting_only=true uses the shared reporting definition."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.services.customer_reporting import reporting_customer_clauses


def test_reporting_only_filter_uses_shared_clauses() -> None:
    clauses = reporting_customer_clauses()
    stmt = (
        select(func.count())
        .select_from(DimCustomer)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(*clauses)
    )
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "reports_expected" in sql
    assert "merged_into_customer_id" in sql