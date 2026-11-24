"""CPOR case list filters: reporting customers and official promotion types."""

from __future__ import annotations

from sqlalchemy import select

from app.api.v1.endpoints import cpor_cases
from app.models.cpor import CporCase
from app.models.dimensions import DimCustomer


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()


def test_apply_case_filters_reporting_only_uses_shared_definition():
    stmt = select(CporCase, DimCustomer).join(DimCustomer, DimCustomer.id == CporCase.customer_id)
    out = cpor_cases._apply_case_filters(
        None,
        stmt,
        status=None,
        customer_id=None,
        distributor_id=None,
        product_id=None,
        business_unit=None,
        window_from=None,
        window_to=None,
        test_data="commercial",
        q=None,
        evidence_basis=None,
        reporting_only=True,
        official_promotion_types=False,
    )
    sql = _sql(out)
    assert "customer_report_config" in sql
    assert "reports_expected" in sql
    assert "merged_into_customer_id" in sql


def test_apply_case_filters_official_promotion_types():
    stmt = select(CporCase, DimCustomer).join(DimCustomer, DimCustomer.id == CporCase.customer_id)
    out = cpor_cases._apply_case_filters(
        None,
        stmt,
        status=None,
        customer_id=None,
        distributor_id=None,
        product_id=None,
        business_unit=None,
        window_from=None,
        window_to=None,
        test_data="commercial",
        q=None,
        evidence_basis=None,
        reporting_only=False,
        official_promotion_types=True,
    )
    sql = _sql(out)
    assert "sell out pp" in sql or "promotion_type" in sql