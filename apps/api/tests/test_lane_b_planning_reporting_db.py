"""Reporting-only header counts and customer chart regressions for lane B.

Run on cip_test through the coordinator. Fixture writes stay inside an outer
rolled-back transaction; teardown checks that none survived. The production
overview queries and execution reporting filter are exercised against PostgreSQL.
Only execution evidence collection is mocked.
"""

from __future__ import annotations

import secrets
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints.planning import get_planning_overview
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.services import planning_overview as overview
from app.services.commercial_planner import plan_vs_executed as pve
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session

PERIOD_START = date(2098, 7, 1)
EMPTY_EXECUTION = {
    "period": None,
    "fill_rate": None,
    "planned_units_execution": 0.0,
    "shipped_units_in_plan": 0.0,
    "by_customer": [],
}


@pytest.fixture
async def session():
    tags: list[str] = []
    async with rolled_back_async_session() as db:
        db.info["lane_b_tags"] = tags
        yield db

    for tag in tags:
        customer_ids = select(DimCustomer.id).where(DimCustomer.code.like(f"LB-{tag}-%"))
        case_ids = select(CommercialLineupCase.id).where(
            CommercialLineupCase.file_name == f"LB-{tag}.xlsx"
        )
        counts = await leftover_counts(
            {
                "customers": select(func.count())
                .select_from(DimCustomer)
                .where(DimCustomer.id.in_(customer_ids)),
                "configs": select(func.count())
                .select_from(CustomerReportConfig)
                .where(CustomerReportConfig.customer_id.in_(customer_ids)),
                "cases": select(func.count())
                .select_from(CommercialLineupCase)
                .where(CommercialLineupCase.id.in_(case_ids)),
                "lines": select(func.count())
                .select_from(CommercialLineupLine)
                .where(CommercialLineupLine.case_id.in_(case_ids)),
            }
        )
        assert counts == dict.fromkeys(counts, 0), f"fixture rows survived rollback: {counts}"


async def _world(db):
    tag = secrets.token_hex(4)
    db.info["lane_b_tags"].append(tag)
    customers = {
        key: DimCustomer(
            code=f"LB-{tag}-{key}",
            name=f"Fixture {key} {tag}",
            tenant_id=f"lb-{tag}",
        )
        for key in ("reporting", "off", "merged", "missing")
    }
    db.add_all(customers.values())
    await db.flush()
    customers["merged"].merged_into_customer_id = customers["reporting"].id
    reporting_config = CustomerReportConfig(
        customer_id=customers["reporting"].id,
        reports_expected=True,
    )
    db.add_all(
        [
            reporting_config,
            CustomerReportConfig(customer_id=customers["off"].id, reports_expected=False),
            CustomerReportConfig(customer_id=customers["merged"].id, reports_expected=True),
        ]
    )

    keys = (
        "mixed",
        "reporting",
        "off",
        "merged",
        "missing",
        "unattributed",
        "retired_lines",
        "cancelled",
        "replaced",
        "superseded",
    )
    cases = {
        key: CommercialLineupCase(
            file_name=f"LB-{tag}.xlsx",
            period_label=f"LB-{tag}-{key}",
            inferred_period_start=PERIOD_START,
            commercial_status=key if key in ("cancelled", "superseded") else "accepted",
        )
        for key in keys
    }
    db.add_all(cases.values())
    await db.flush()
    # Even an accepted case is inactive when a successor replaces it.
    cases["replaced"].superseded_by_case_id = cases["reporting"].id

    def add_line(case_key, customer_key, units, *, row_status="imported"):
        db.add(
            CommercialLineupLine(
                case_id=cases[case_key].id,
                customer_id=customers[customer_key].id if customer_key else None,
                quantity_units=units,
                row_status=row_status,
            )
        )

    # A qualifying case must still exclude its non-reporting and retired lines.
    add_line("mixed", "reporting", 10)
    add_line("mixed", "reporting", 20)
    add_line("mixed", "off", 100)
    add_line("mixed", "merged", 1000)
    add_line("mixed", "missing", 10000)
    add_line("mixed", None, 100000)
    add_line("mixed", "reporting", 1000000, row_status="superseded")
    add_line("reporting", "reporting", 7)

    for key in ("off", "merged", "missing"):
        add_line(key, key, 100)
    add_line("unattributed", None, 100)
    add_line("retired_lines", "reporting", 100, row_status="superseded")
    for key in ("cancelled", "replaced", "superseded"):
        add_line(key, "reporting", 100)

    await db.flush()
    return SimpleNamespace(
        customers=customers,
        cases=cases,
        reporting_config=reporting_config,
    )


@pytest.mark.anyio
async def test_header_counts_only_reporting_lines_and_cases_with_active_reporting_lines(session):
    with patch.object(
        overview,
        "_shipped_vs_plan",
        AsyncMock(return_value=EMPTY_EXECUTION),
    ):
        before = await get_planning_overview(db=session, user=None)
        assert before["data_unavailable"] is False
        world = await _world(session)
        after = await get_planning_overview(db=session, user=None)

        assert after["data_unavailable"] is False
        assert after["cases"] - before["cases"] == 2
        assert after["lines"] - before["lines"] == 3
        assert after["plan_units"] - before["plan_units"] == 37
        assert set(after["period_labels"]) - set(before["period_labels"]) == {
            world.cases["mixed"].period_label,
            world.cases["reporting"].period_label,
        }

        # Turning off the only eligible fixture customer removes every fixture
        # case and line. Missing configs and merged-away true flags cannot qualify.
        world.reporting_config.reports_expected = False
        await session.flush()
        disabled = await get_planning_overview(db=session, user=None)
        assert disabled["data_unavailable"] is False
        for field in ("cases", "lines", "plan_units", "period_labels"):
            assert disabled[field] == before[field]


@pytest.mark.anyio
async def test_overview_chart_uses_real_reporting_membership_before_customer_ranking(session):
    world = await _world(session)
    case = world.cases["mixed"]
    products = [
        {
            "customer_id": world.customers["reporting"].id,
            "planned_units": 10,
            "shipped_units": 4,
        },
        {
            "customer_id": world.customers["off"].id,
            "planned_units": 1000,
            "shipped_units": 900,
        },
        {
            "customer_id": world.customers["merged"].id,
            "planned_units": 2000,
            "shipped_units": 1900,
        },
        {
            "customer_id": world.customers["missing"].id,
            "planned_units": 3000,
            "shipped_units": 2900,
        },
        {"customer_id": None, "planned_units": 2, "shipped_units": 1},
    ]
    reconciliation = {
        case.id: {
            "customers": [
                {"customer_id": customer.id, "label": customer.name}
                for customer in world.customers.values()
            ],
            "products": products,
        }
    }

    # Keep collect_execution_rows, its reporting SELECT, the scorecard and chart
    # aggregation real. Only the upstream evidence and default period are fixed.
    with (
        patch(
            "app.services.commercial_planner.po_management.coverage",
            AsyncMock(return_value={"groups": []}),
        ),
        patch.object(pve, "lineup_linked_year_quarters", AsyncMock(return_value=set())),
        patch.object(pve, "resolve_default_period", return_value="98Q3"),
        patch.object(pve, "_linked_cases", AsyncMock(return_value=[case])),
        patch.object(pve, "reconcile_cases", AsyncMock(return_value=reconciliation)),
        patch.object(pve, "_attach_product_catalog_fields", AsyncMock()),
    ):
        result = await overview._shipped_vs_plan(session)

    customer_rows = [row for row in result["by_customer"] if row["customer_id"] is not None]
    assert customer_rows == [
        {
            "customer": world.customers["reporting"].name,
            "customer_id": world.customers["reporting"].id,
            "plan": 10.0,
            "shipped": 4.0,
        }
    ]
    # Preserve the existing separate evidence bucket; it is never a customer.
    assert [row for row in result["by_customer"] if row["customer_id"] is None] == [
        {"customer": "Unattributed", "customer_id": None, "plan": 2.0, "shipped": 1.0}
    ]
