"""Line-up item payloads expose Product Master product_line without inferred BU values.

No database connections. Existing reporting-read and planning-overview tests cover
the shared reporting predicate used by the page header, chart and item list.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints import lineup
from app.models.dimensions import DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _item(product_line: str | None, *, linked: bool = True) -> FactLineupPlanItem:
    product = DimProduct(
        id=11,
        sku="PREFIX-ITEM",
        name="Fixture product",
        product_line=product_line,
        business_unit="Different legacy BU",
    )
    customer = DimCustomer(id=3, code="FIXTURE-CODE", name="Fixture customer")
    return FactLineupPlanItem(
        id=7,
        customer_id=customer.id,
        customer=customer,
        product_id=product.id,
        product=product if linked else None,
        period_start=date(2026, 1, 1),
        period_label="26Q1",
        planned_volume_units=1250,
        approval_status="draft",
        overlap_cannibalization_flag=False,
        whitespace_gap_flag=False,
    )


async def _read(item: FactLineupPlanItem):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = [item]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    rows = await lineup.list_lineup_items(
        customer_id=None,
        channel_id=None,
        period_start=None,
        db=db,
    )
    return rows[0], db.execute.await_args.args[0]


@pytest.mark.anyio
async def test_item_read_exposes_product_line_and_planned_units_without_extra_queries():
    row, statement = await _read(_item(" Catalogue line "))
    assert row["product_line"] == "Catalogue line"
    assert row["business_unit_reason"] is None
    assert row["planned_volume_units"] == 1250.0
    assert row["customer_name"] == "Fixture customer"
    assert row["customer_code"] == "FIXTURE-CODE"

    sql = str(statement.compile(dialect=postgresql.dialect())).lower()
    assert "fact_lineup_plan_item.customer_id in (select" in sql
    assert "reports_expected is true" in sql
    assert "merged_into_customer_id is null" in sql


@pytest.mark.anyio
@pytest.mark.parametrize("product_line", [None, "", "   "])
async def test_missing_product_line_is_explained_without_sku_channel_or_legacy_bu_fallback(
    product_line,
):
    row, _statement = await _read(_item(product_line))
    assert row["product_line"] is None
    assert row["business_unit_reason"] == "Product Master product line is empty"
    assert row["planned_volume_units"] == 1250.0


@pytest.mark.anyio
async def test_missing_product_relationship_has_a_distinct_reason():
    row, _statement = await _read(_item(None, linked=False))
    assert row["product_line"] is None
    assert row["business_unit_reason"] == "Product is not linked to Product Master"
    assert row["sku"] is None


@pytest.mark.anyio
async def test_zero_planned_units_remain_zero():
    item = _item("Catalogue line")
    item.planned_volume_units = 0
    row, _statement = await _read(item)
    assert row["planned_volume_units"] == 0.0
    assert row["product_line"] == "Catalogue line"
