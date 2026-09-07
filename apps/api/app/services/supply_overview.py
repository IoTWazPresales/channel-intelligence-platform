"""Read-only Supply & Inbound headline grains. Callers must print current_database() first."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user
from app.services.commercial_planner.po_management import coverage as po_coverage

# ISO Monday in Africa/Johannesburg — same grain as Movement / Data stewardship week keys.
_ISO_WEEK_START_SAST = """
((now() AT TIME ZONE 'Africa/Johannesburg')::date
 - EXTRACT(ISODOW FROM (now() AT TIME ZONE 'Africa/Johannesburg')::date)::int
 + 1)
"""

_TODAY_SAST = "(now() AT TIME ZONE 'Africa/Johannesburg')::date"


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
                      ) AS open_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE status IS DISTINCT FROM 'received'
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
                      ) AS pipeline_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'open_order'
                      ), 0) AS pipeline_units,
                      count(*) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'shipped'
                      ) AS shipped_lines,
                      coalesce(sum(quantity) FILTER (
                        WHERE pod_date IS NULL AND line_state = 'shipped'
                      ), 0) AS shipped_units,
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
        po_by_distributor = []

    try:
        po = await po_coverage(db)
    except Exception:
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

    job_caption = "No inbound_shipments job on file"
    if last_job is not None:
        created = last_job["created_at"]
        job_caption = (
            f"Last inbound job {last_job['file_name'] or '(unnamed)'} "
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
                "state": "Landed (POD)",
                "count": int(row["landed_lines"] or 0),
                "units": float(row["landed_units"] or 0),
            },
        ],
        "po_by_distributor": po_by_distributor,
        "labels": {
            "open_lines": "Open shipments",
            "eta_past_no_pod_lines": "Unreceived past ETA",
            "landed_pod_iso_week": "Received this week",
            "po_coverage": "PO coverage",
            "pipeline_units": "Backlog units",
        },
        "captions": {
            "open_lines": "status ≠ received (pipeline + shipped, no POD) — not the lab shipped+arrived fixture",
            "eta_past_no_pod_lines": (
                f"pod_date is null and eta_date < today SAST"
                f"{f'; oldest {oldest_days} days ({oldest_eta_s})' if oldest_days is not None else ''}"
                f". Overlaps pipeline and shipped; not a fifth lifecycle bar. "
                f"Commercial overdue (promise window) is {overdue} — different grain."
            ),
            "landed_pod_iso_week": (
                f"POD date this ISO week (Monday 00:00 SAST). {job_caption}"
            ),
            "po_coverage": (
                f"{linked} of {observed} observed POs linked to an active lineup case — "
                "not plan units covered"
            ),
            "pipeline_units": "open_order units still in the pipeline (line_state), not lab plan backlog",
        },
        "number_class": {
            "open_lines": "iii",
            "eta_past_no_pod_lines": "iii",
            "landed_pod_iso_week": "iii",
            "po_coverage": "iii",
            "pipeline_units": "iii",
        },
    }
