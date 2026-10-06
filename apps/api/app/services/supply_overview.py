"""Read-only Supply & Inbound headline grains. Callers must print current_database() first."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimDistributor
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    active_lineup_line_filters,
)
from app.services.commercial_planner.po_management import coverage as po_coverage

logger = logging.getLogger(__name__)

# ISO Monday in Africa/Johannesburg — same grain as Movement / Data stewardship week keys.
_ISO_WEEK_START_SAST = """
((now() AT TIME ZONE 'Africa/Johannesburg')::date
 - EXTRACT(ISODOW FROM (now() AT TIME ZONE 'Africa/Johannesburg')::date)::int
 + 1)
"""

_TODAY_SAST = "(now() AT TIME ZONE 'Africa/Johannesburg')::date"

# An open-order fact does not count when the same order line is already shipped.
# Strict pair: operating unit + order number + item code. A looser join is not a pair.
_OPEN_HAS_SHIPPED_TWIN = """
EXISTS (
  SELECT 1
  FROM fact_inbound_shipment shipped_twin
  WHERE shipped_twin.tenant_id = fact_inbound_shipment.tenant_id
    AND shipped_twin.id <> fact_inbound_shipment.id
    AND lower(shipped_twin.line_state) = 'shipped'
    AND trim(coalesce(fact_inbound_shipment.order_no, '')) <> ''
    AND trim(coalesce(fact_inbound_shipment.item_code, '')) <> ''
    AND lower(trim(coalesce(shipped_twin.operating_unit, '')))
        = lower(trim(coalesce(fact_inbound_shipment.operating_unit, '')))
    AND lower(trim(shipped_twin.order_no)) = lower(trim(fact_inbound_shipment.order_no))
    AND lower(trim(shipped_twin.item_code)) = lower(trim(fact_inbound_shipment.item_code))
)
"""


def shape_plan_unit_po_coverage(rows: list[tuple[Any, ...]]) -> list[dict[str, Any]]:
    """Plan units vs case-linked POs. Covered is the full line quantity, not PO quantity."""
    shaped: list[dict[str, Any]] = []
    for distributor_id, distributor, plan_units, covered_units in rows:
        plan = float(plan_units or 0)
        covered_qty = float(covered_units or 0)
        shaped.append(
            {
                "distributor_id": int(distributor_id) if distributor_id is not None else None,
                "distributor": str(distributor),
                "plan_units": plan,
                "covered_units": covered_qty,
                "backlog_units": plan - covered_qty,
                "covered": (covered_qty / plan) if plan else 0.0,
            }
        )
    return shaped


async def plan_unit_po_coverage_by_distributor(db: AsyncSession) -> list[dict[str, Any]]:
    """Derived read. Nothing is stored.

    Plan units are active lineup line quantities. A line is covered when its case
    has a linked purchase order. Backlog is the uncovered quantity. Distributor
    is the lineup line's distributor, not the purchase order's.
    """
    linked = select(CommercialLineupCasePo.case_id).distinct().subquery()
    distributor_name = func.coalesce(DimDistributor.name, "Unmapped distributor")
    covered_qty = func.coalesce(
        func.sum(CommercialLineupLine.quantity_units).filter(linked.c.case_id.is_not(None)),
        0,
    )
    plan_qty = func.coalesce(func.sum(CommercialLineupLine.quantity_units), 0)
    stmt = (
        select(
            CommercialLineupLine.distributor_id,
            distributor_name,
            plan_qty,
            covered_qty,
        )
        .select_from(CommercialLineupLine)
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
        .outerjoin(DimDistributor, DimDistributor.id == CommercialLineupLine.distributor_id)
        .outerjoin(linked, linked.c.case_id == CommercialLineupCase.id)
        .where(*active_lineup_case_filters(), *active_lineup_line_filters())
        .group_by(CommercialLineupLine.distributor_id, DimDistributor.name)
        .order_by(plan_qty.desc(), distributor_name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return shape_plan_unit_po_coverage(rows)


async def supply_overview(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    tenant = tenant_id_from_user(user)
    dbname = (await db.execute(text("SELECT current_database()"))).scalar()
    try:
        row = (
            await db.execute(
                text(
                    f"""
                    SELECT
                      :tenant AS tenant_id,
                      count(*) FILTER (
                        WHERE status IS DISTINCT FROM 'received'
                          AND NOT (
                            lower(line_state) = 'open_order'
                            AND {_OPEN_HAS_SHIPPED_TWIN}
                          )
                      ) AS open_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE status IS DISTINCT FROM 'received'
                          AND NOT (
                            lower(line_state) = 'open_order'
                            AND {_OPEN_HAS_SHIPPED_TWIN}
                          )
                      ), 0) AS open_units,
                      count(*) FILTER (
                        WHERE pod_date IS NULL
                          AND eta_date IS NOT NULL
                          AND eta_date < {_TODAY_SAST}
                      ) AS eta_past_no_pod_lines,
                      min(eta_date) FILTER (
                        WHERE pod_date IS NULL
                          AND eta_date IS NOT NULL
                          AND eta_date < {_TODAY_SAST}
                      ) AS oldest_eta_past,
                      max(({_TODAY_SAST} - eta_date)) FILTER (
                        WHERE pod_date IS NULL
                          AND eta_date IS NOT NULL
                          AND eta_date < {_TODAY_SAST}
                      ) AS oldest_days_past_eta,
                      count(*) FILTER (
                        WHERE pod_date IS NOT NULL
                          AND pod_date >= {_ISO_WEEK_START_SAST}
                      ) AS landed_pod_iso_week,
                      count(*) FILTER (WHERE pod_date IS NOT NULL) AS landed_lines,
                      coalesce(sum(quantity) FILTER (WHERE pod_date IS NOT NULL), 0) AS landed_units,
                      count(*) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'open_order'
                          AND NOT ({_OPEN_HAS_SHIPPED_TWIN})
                      ) AS pipeline_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'open_order'
                          AND NOT ({_OPEN_HAS_SHIPPED_TWIN})
                      ), 0) AS pipeline_units,
                      count(*) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'shipped'
                      ) AS shipped_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'shipped'
                      ), 0) AS shipped_units,
                      count(*) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'arrived'
                      ) AS arrived_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'arrived'
                      ), 0) AS arrived_units,
                      count(*) FILTER (
                        WHERE status = 'scheduled'
                          AND pod_date IS NULL
                          AND promise_date IS NOT NULL
                          AND promise_date < {_TODAY_SAST}
                          AND promise_date >= {_TODAY_SAST} - 180
                          AND eta_date IS NOT NULL
                          AND eta_date >= {_TODAY_SAST}
                          AND eta_date <= {_TODAY_SAST} + 90
                      ) AS overdue_commercial_lines
                    FROM fact_inbound_shipment
                    WHERE tenant_id = :tenant
                    """
                ),
                {"tenant": tenant},
            )
        ).mappings().one()
    except Exception:
        logger.exception("supply overview read failed tenant_id=%s", tenant)
        return {
            "database": dbname,
            "tenant_id": tenant,
            "data_unavailable": True,
            "labels": {},
            "captions": {},
        }

    last_job = (
        await db.execute(
            text(
                """
                SELECT file_name, created_at, status, stage
                FROM import_job
                WHERE template_slug = 'inbound_shipments'
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        )
    ).mappings().first()

    po_by_distributor: list[dict[str, Any]] = []
    try:
        dist_rows = (
            await db.execute(
                text(
                    """
                    SELECT coalesce(d.name, 'Unmapped distributor') AS distributor,
                           count(*)::int AS observed_pos,
                           count(*) FILTER (WHERE linked.purchase_order_id IS NOT NULL)::int AS linked_pos
                    FROM purchase_order po
                    LEFT JOIN dim_distributor d ON d.id = po.distributor_id
                    LEFT JOIN (
                      SELECT DISTINCT cl.purchase_order_id
                      FROM commercial_lineup_case_po cl
                      JOIN commercial_lineup_case c ON c.id = cl.case_id
                      WHERE c.superseded_by_case_id IS NULL
                        AND c.commercial_status NOT IN ('cancelled', 'superseded')
                    ) linked ON linked.purchase_order_id = po.id
                    GROUP BY 1
                    ORDER BY observed_pos DESC
                    LIMIT 12
                    """
                )
            )
        ).mappings().all()
        po_by_distributor = [
            {
                "distributor": r["distributor"],
                "observed_pos": int(r["observed_pos"] or 0),
                "linked_pos": int(r["linked_pos"] or 0),
                "covered": (
                    float(r["linked_pos"] or 0) / float(r["observed_pos"])
                    if int(r["observed_pos"] or 0)
                    else 0.0
                ),
            }
            for r in dist_rows
        ]
    except Exception:
        logger.exception("supply overview purchase-order coverage read failed")
        po_by_distributor = []

    plan_unit_po_by_distributor: list[dict[str, Any]] = []
    try:
        plan_unit_po_by_distributor = await plan_unit_po_coverage_by_distributor(db)
    except Exception:
        logger.exception("supply overview plan-unit coverage read failed")
        plan_unit_po_by_distributor = []

    try:
        po = await po_coverage(db)
    except Exception:
        logger.exception("supply overview purchase-order total read failed")
        po = {
            "total_pos_observed": 0,
            "total_pos_linked": 0,
            "data_unavailable": True,
        }

    observed = int(po.get("total_pos_observed") or 0)
    linked = int(po.get("total_pos_linked") or 0)
    po_ratio = (linked / observed) if observed else None

    open_lines = int(row["open_lines"] or 0)
    eta_past = int(row["eta_past_no_pod_lines"] or 0)
    oldest_days = int(row["oldest_days_past_eta"] or 0) if row["oldest_days_past_eta"] is not None else None
    landed_week = int(row["landed_pod_iso_week"] or 0)
    pipeline_units = float(row["pipeline_units"] or 0)
    overdue = int(row["overdue_commercial_lines"] or 0)

    job_caption = "No shipment import on file"
    if last_job is not None:
        created = last_job["created_at"]
        job_caption = (
            f"Last shipment file {last_job['file_name'] or '(unnamed)'} "
            f"({last_job['stage'] or last_job['status']}"
            f"{', ' + created.isoformat() if created is not None else ''})"
        )

    oldest_eta = row["oldest_eta_past"]
    oldest_eta_s = oldest_eta.isoformat() if oldest_eta is not None else None

    return {
        "database": dbname,
        "tenant_id": tenant,
        "data_unavailable": False,
        "open_lines": open_lines,
        "open_units": float(row["open_units"] or 0),
        "eta_past_no_pod_lines": eta_past,
        "oldest_eta_past": oldest_eta_s,
        "oldest_days_past_eta": oldest_days,
        "landed_pod_iso_week": landed_week,
        "pipeline_lines": int(row["pipeline_lines"] or 0),
        "pipeline_units": pipeline_units,
        "shipped_lines": int(row["shipped_lines"] or 0),
        "shipped_units": float(row["shipped_units"] or 0),
        "landed_lines": int(row["landed_lines"] or 0),
        "landed_units": float(row["landed_units"] or 0),
        "arrived_lines": int(row["arrived_lines"] or 0),
        "arrived_units": float(row["arrived_units"] or 0),
        "overdue_commercial_lines": overdue,
        "po_observed": observed,
        "po_linked": linked,
        "po_coverage_ratio": po_ratio,
        "po_data_unavailable": bool(po.get("data_unavailable")),
        "lifecycle": [
            {
                "state": "Pipeline (open order)",
                "count": int(row["pipeline_lines"] or 0),
                "units": float(row["pipeline_units"] or 0),
            },
            {
                "state": "Shipped, not landed",
                "count": int(row["shipped_lines"] or 0),
                "units": float(row["shipped_units"] or 0),
            },
            {
                "state": "Arrived, no POD",
                "count": int(row["arrived_lines"] or 0),
                "units": float(row["arrived_units"] or 0),
            },
            {
                "state": "Landed (POD)",
                "count": int(row["landed_lines"] or 0),
                "units": float(row["landed_units"] or 0),
            },
        ],
        "po_by_distributor": po_by_distributor,
        "plan_unit_po_by_distributor": plan_unit_po_by_distributor,
        "labels": {
            "open_lines": "Open shipments",
            "eta_past_no_pod_lines": "Unreceived past ETA",
            "landed_pod_iso_week": "Received this week",
            "po_coverage": "PO coverage",
            "pipeline_units": "Backlog units",
        },
        "captions": {
            "open_lines": "Still open: on order, shipped, or arrived, and no proof of delivery yet",
            "eta_past_no_pod_lines": (
                f"Past the expected date, and no proof of delivery"
                f"{f'; oldest {oldest_days} days ({oldest_eta_s})' if oldest_days is not None else ''}"
                f". These rows are already inside the open count. "
                f"A separate commercial-overdue count (promise window) is {overdue}."
            ),
            "landed_pod_iso_week": (
                f"Proof of delivery dated this week (from Monday, South Africa time). {job_caption}"
            ),
            "po_coverage": (
                f"{linked} of {observed} purchase orders linked to an active lineup case. "
                "This is order count, not plan units."
            ),
            "plan_unit_po_coverage": (
                "Active lineup quantity by distributor. A line counts as covered when its case "
                "has a linked purchase order, and the whole line quantity counts. Backlog is "
                "the quantity still uncovered. This is not the purchase-order count above, "
                "and it is not the quantity written on the purchase order."
            ),
            "pipeline_units": "Units still on order. Arrived units are not in this figure.",
        },
        "number_class": {
            "open_lines": "iii",
            "eta_past_no_pod_lines": "iii",
            "landed_pod_iso_week": "iii",
            "po_coverage": "iii",
            "pipeline_units": "iii",
        },
    }
