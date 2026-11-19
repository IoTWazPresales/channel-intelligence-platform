"""Warren 2026-11-19: line-up file writes refuse rows for non-reporting customers (cip_test).

Real session, rolled back at the end of each test. Covers the two writers that read customers from a
file: the bulk ``fact_lineup_plan_item`` upsert and the shared line-up file parser that the unified
import, the parse-apply route and the bulk backfill all run.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem
from app.services.commercial_planner.lineup_case_parser import (
    parse_current_lineup_file,
    preview_current_lineup_file,
)
from app.services.lineup.bulk import bulk_upsert_lineup_items
from sqlalchemy import select


@pytest.fixture
async def session():
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.rollback()


async def _world(db, tag: str):
    tenant = f"t-{tag}"
    reporting = DimCustomer(code=f"RG-{tag}-R", name=f"Reporting {tag}", tenant_id=tenant)
    silent = DimCustomer(code=f"RG-{tag}-S", name=f"Silent {tag}", tenant_id=tenant)
    no_config = DimCustomer(code=f"RG-{tag}-N", name=f"NoConfig {tag}", tenant_id=tenant)
    product = DimProduct(sku=f"RG-{tag}-SKU", name=f"Product {tag}", tenant_id=tenant)
    db.add_all([reporting, silent, no_config, product])
    await db.flush()
    db.add(CustomerReportConfig(customer_id=reporting.id, reports_expected=True))
    db.add(CustomerReportConfig(customer_id=silent.id, reports_expected=False))
    await db.flush()
    return reporting, silent, no_config, product


@pytest.mark.anyio
async def test_bulk_upsert_writes_reporting_rows_and_refuses_the_rest_with_a_reason(session):
    tag = secrets.token_hex(3)
    reporting, silent, no_config, product = await _world(session, tag)
    rows = [
        {"customer_code": c.code, "sku": product.sku, "period_start": "2026-10-01"}
        for c in (reporting, silent, no_config)
    ]
    out = await bulk_upsert_lineup_items(session, rows, replace_matching=False)
    assert (out["inserted"], out["refused"], out["errors"]) == (1, 2, 0)
    refused = [r for r in out["results"] if r["status"] == "refused"]
    assert {r["reason"] for r in refused} == {"customer_not_reporting"}
    written = (
        (
            await session.execute(
                select(FactLineupPlanItem.customer_id).where(
                    FactLineupPlanItem.customer_id.in_([reporting.id, silent.id, no_config.id])
                )
            )
        )
        .scalars()
        .all()
    )
    assert written == [reporting.id]


@pytest.mark.anyio
async def test_file_parser_writes_reporting_rows_and_reports_refused_rows(session):
    tag = secrets.token_hex(3)
    reporting, silent, no_config, product = await _world(session, tag)
    case = CommercialLineupCase(
        period_label="26Q4",
        inferred_period_start=date(2026, 10, 1),
        commercial_status="draft_imported",
        business_unit="BU",
    )
    session.add(case)
    await session.flush()
    csv = (
        "sku,qty,customer\n"
        f"{product.sku},5,{reporting.code}\n"
        f"{product.sku},6,{silent.code}\n"
        f"{product.sku},7,{no_config.code}\n"
    ).encode()

    result = await parse_current_lineup_file(
        session,
        case.id,
        "lineup.csv",
        csv,
        template_slug="unified_lineup",
        source_code="unified_lineup_system",
    )
    assert result.line_count == 1 and result.refused_count == 2
    assert {r["reason"] for r in result.refused_rows} == {"customer_not_reporting"}
    assert any("2 row(s) refused" in w for w in result.warnings)
    lines = (
        (
            await session.execute(
                select(CommercialLineupLine.customer_id).where(
                    CommercialLineupLine.case_id == case.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert lines == [reporting.id]


@pytest.mark.anyio
async def test_parse_preview_counts_the_rows_an_apply_would_refuse(session):
    tag = secrets.token_hex(3)
    reporting, silent, _no_config, product = await _world(session, tag)
    csv = (
        f"sku,qty,customer\n{product.sku},5,{reporting.code}\n{product.sku},6,{silent.code}\n"
    ).encode()
    preview = await preview_current_lineup_file(session, "lineup.csv", csv)
    assert preview.refused_not_reporting_rows == 1
    flagged = [
        r for r in preview.rows if "customer_not_reporting" in (r.get("diagnostic_codes") or [])
    ]
    assert [r["customer_id"] for r in flagged] == [silent.id]
