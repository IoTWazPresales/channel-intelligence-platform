"""Warren 2026-11-19: line-up file writes refuse rows for non-reporting customers (cip_test).

Real session inside an outer transaction that is rolled back at the end of each test; the services'
own commits only release savepoints (``tests/rolled_back_async_session.py``), and teardown proves in
a fresh session that none of the test's synthetic rows remain (PR #122 round 2, B3). Covers the two
writers that read customers from a file: the bulk ``fact_lineup_plan_item`` upsert and the shared
line-up file parser that the unified import, the parse-apply route and the bulk backfill all run.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.ingestion import ImportJob
from app.models.lineup import FactLineupPlanItem
from app.services.commercial_planner.lineup_case_parser import (
    parse_current_lineup_file,
    preview_current_lineup_file,
)
from app.services.lineup.bulk import bulk_upsert_lineup_items
from sqlalchemy import func, or_, select
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        db.info["fixture"] = {"tags": [], "case_ids": [], "job_ids": []}
        yield db
        created = dict(db.info["fixture"])
    await _assert_no_fixture_rows_left(created)


async def _assert_no_fixture_rows_left(created: dict) -> None:
    """B3: after teardown a fresh session finds none of the test's synthetic rows."""
    codes = [f"RG-{tag}-%" for tag in created["tags"]] or ["RG-no-fixture-%"]
    case_ids = created["case_ids"] or [-1]
    job_ids = created["job_ids"] or [-1]
    fixture_customers = select(DimCustomer.id).where(
        or_(*[DimCustomer.code.like(c) for c in codes])
    )
    counts = await leftover_counts(
        {
            "dim_customer": select(func.count()).where(DimCustomer.id.in_(fixture_customers)),
            "dim_product": select(func.count()).where(
                or_(*[DimProduct.sku.like(c) for c in codes])
            ),
            "customer_report_config": select(func.count()).where(
                CustomerReportConfig.customer_id.in_(fixture_customers)
            ),
            "fact_lineup_plan_item": select(func.count()).where(
                FactLineupPlanItem.customer_id.in_(fixture_customers)
            ),
            "commercial_lineup_case": select(func.count()).where(
                CommercialLineupCase.id.in_(case_ids)
            ),
            "commercial_lineup_line": select(func.count()).where(
                CommercialLineupLine.case_id.in_(case_ids)
            ),
            "import_job": select(func.count()).where(ImportJob.id.in_(job_ids)),
        }
    )
    assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


async def _world(db, tag: str):
    db.info["fixture"]["tags"].append(tag)
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
    session.info["fixture"]["case_ids"].append(case.id)
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
    session.info["fixture"]["job_ids"].append(result.import_job_id)
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


@pytest.mark.anyio
async def test_a_merged_away_customer_is_not_reporting_anywhere(session):
    """Fix round 1, item 3: one definition (reports expected AND not merged) for every check."""
    from app.services.lineup.new_customer_proposal import (
        ProposalError,
        ensure_reporting_customer,
        list_reporting_customers,
        reporting_customer_ids,
    )

    tag = secrets.token_hex(3)
    reporting, silent, _no_config, _product = await _world(session, tag)
    assert reporting.id in await reporting_customer_ids(session)

    reporting.merged_into_customer_id = silent.id  # merged away, flag still ticked
    await session.flush()

    assert reporting.id not in await reporting_customer_ids(session)
    listed = await session.run_sync(lambda s: {c["id"] for c in list_reporting_customers(s)})
    assert reporting.id not in listed

    def _check(sync_session):
        with pytest.raises(ProposalError) as err:
            ensure_reporting_customer(sync_session, reporting.id)
        return err.value.code

    assert await session.run_sync(_check) == "customer_not_reporting"
