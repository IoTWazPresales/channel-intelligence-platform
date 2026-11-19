"""PR #122 round 1, B1: a replacement with no eligible rows keeps the existing line-up (cip_test).

Real session, rolled back at the end of each test. The replacement case is parsed by the shared file
parser with ``replaces_case_id`` in its job's parse options (what the bulk backfill apply now sets).
When the reporting gate refuses every row the existing case stays current with its PO links; when a
row is kept the existing case is superseded and its PO links are carried to the replacement.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.current_lineup_seed import ensure_lineup_import_seed
from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file
from sqlalchemy import func, select

TEMPLATE = "unified_lineup"
SOURCE = "unified_lineup_system"


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
    reporting = DimCustomer(code=f"RP-{tag}-R", name=f"Reporting {tag}", tenant_id=tenant)
    silent = DimCustomer(code=f"RP-{tag}-S", name=f"Silent {tag}", tenant_id=tenant)
    product = DimProduct(sku=f"RP-{tag}-SKU", name=f"Product {tag}", tenant_id=tenant)
    db.add_all([reporting, silent, product])
    await db.flush()
    db.add(CustomerReportConfig(customer_id=reporting.id, reports_expected=True))
    db.add(CustomerReportConfig(customer_id=silent.id, reports_expected=False))
    await db.flush()

    existing = CommercialLineupCase(
        period_label="26Q4",
        inferred_period_start=date(2026, 10, 1),
        commercial_status="po_issued",
        business_unit="BU",
    )
    replacement = CommercialLineupCase(
        period_label="26Q4",
        inferred_period_start=date(2026, 10, 1),
        commercial_status="draft_imported",
        business_unit="BU",
    )
    db.add_all([existing, replacement])
    await db.flush()
    po = PurchaseOrder(po_number_raw=f"RP{tag}", po_number_norm=f"RP{tag}")
    db.add(po)
    await db.flush()
    db.add(CommercialLineupCasePo(case_id=existing.id, purchase_order_id=po.id))
    await db.flush()
    return reporting, silent, product, existing, replacement


async def _replacing_job(db, replaces_case_id: int) -> int:
    await ensure_lineup_import_seed(db, template_slug=TEMPLATE, source_code=SOURCE)
    source = await db.scalar(
        select(SourceDefinition)
        .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
        .where(ImportTemplate.slug == TEMPLATE, SourceDefinition.code == SOURCE)
        .limit(1)
    )
    job = ImportJob(
        source_id=source.id,
        template_slug=TEMPLATE,
        import_mode="apply",
        status="running",
        file_name="lineup.csv",
        staged_metadata={"lineup_parse_options": {"replaces_case_id": int(replaces_case_id)}},
    )
    db.add(job)
    await db.flush()
    return int(job.id)


async def _po_links(db, case_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(CommercialLineupCasePo)
            .where(CommercialLineupCasePo.case_id == case_id)
        )
        or 0
    )


async def _parse(db, replacement, existing, csv: bytes):
    job_id = await _replacing_job(db, existing.id)
    return await parse_current_lineup_file(
        db,
        replacement.id,
        "lineup.csv",
        csv,
        existing_import_job_id=job_id,
        template_slug=TEMPLATE,
        source_code=SOURCE,
    ), job_id


@pytest.mark.anyio
async def test_entirely_refused_replacement_leaves_existing_case_current_with_po_links(session):
    tag = secrets.token_hex(3)
    _reporting, silent, product, existing, replacement = await _world(session, tag)
    csv = (
        f"sku,qty,customer\n{product.sku},5,{silent.code}\n{product.sku},6,{silent.code}\n"
    ).encode()

    result, job_id = await _parse(session, replacement, existing, csv)

    assert result.line_count == 0 and result.refused_count == 2
    await session.refresh(existing)
    assert existing.commercial_status == "po_issued"
    assert existing.superseded_by_case_id is None
    assert await _po_links(session, existing.id) == 1  # untouched
    assert await _po_links(session, replacement.id) == 0  # nothing moved
    lines = await session.scalar(
        select(func.count())
        .select_from(CommercialLineupLine)
        .where(CommercialLineupLine.case_id == replacement.id)
    )
    assert lines == 0
    job = await session.get(ImportJob, job_id)
    note = job.staged_metadata["lineup_replacement"]
    assert note["existing_case_id"] == existing.id and note["superseded"] is False
    assert note["reason"] == "replacement_has_no_eligible_rows" and note["refused_count"] == 2
    assert any("kept" in w for w in result.warnings)


@pytest.mark.anyio
async def test_replacement_that_keeps_a_row_supersedes_and_carries_po_links(session):
    tag = secrets.token_hex(3)
    reporting, silent, product, existing, replacement = await _world(session, tag)
    csv = (
        f"sku,qty,customer\n{product.sku},5,{reporting.code}\n{product.sku},6,{silent.code}\n"
    ).encode()

    result, job_id = await _parse(session, replacement, existing, csv)

    assert result.line_count == 1 and result.refused_count == 1
    await session.refresh(existing)
    assert existing.commercial_status == "superseded"
    assert existing.superseded_by_case_id == replacement.id
    assert await _po_links(session, replacement.id) == 1  # carried (copied)
    assert await _po_links(session, existing.id) == 1  # historical link stays
    job = await session.get(ImportJob, job_id)
    assert job.staged_metadata["lineup_replacement"]["superseded"] is True
