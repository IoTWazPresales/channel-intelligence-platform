"""Cross-job steward queue grouped by ``import_entity_mapping_candidate.entity_type``.

Grouping is SQL ``GROUP BY entity_type`` — not hardcoded Customer/Product/Distributor
sections. Known types may carry a label and an href into an existing job-scoped
engine. Unknown types still appear; missing href is UNCOVERED.

Tenant identity uses ``tenant_id_from_user`` (config), never a queue constant.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user

# Config: resolution path for types that already have an engine. Not UI sections.
# Adding a future importer's type to the queue surface does not require a change here;
# adding a click-through does (one registry row).
STEWARD_QUEUE_RESOLUTION: dict[str, dict[str, str]] = {
    "product_identifier": {
        "label": "DSI product identifier",
        "href_template": "/admin/imports?job={import_job_id}",
    },
    "customer_dealer_token": {
        "label": "DSI customer / dealer token",
        "href_template": "/admin/imports?job={import_job_id}",
    },
    "distributor_token": {
        "label": "DSI distributor token",
        "href_template": "/admin/imports?job={import_job_id}",
    },
    "cst_product_token": {
        "label": "CST product token",
        "href_template": "/admin/imports?job={import_job_id}",
    },
    "cst_location_token": {
        "label": "CST location token",
        "href_template": "/admin/imports?job={import_job_id}",
    },
    "shipment_distributor": {
        "label": "Shipment distributor",
        "href_template": "/admin/shipment-evidence?importJobId={import_job_id}",
    },
    "shipment_customer_token": {
        "label": "Shipment customer token",
        "href_template": "/admin/shipment-evidence?importJobId={import_job_id}",
    },
}

OPEN_CANDIDATE_STATUS = "needs_review"
DEFAULT_ITEM_LIMIT = 2000
MAX_ITEM_LIMIT = 5000


def resolution_href(entity_type: str, import_job_id: int) -> str | None:
    spec = STEWARD_QUEUE_RESOLUTION.get(entity_type)
    if not spec:
        return None
    return spec["href_template"].format(import_job_id=int(import_job_id))


def resolution_label(entity_type: str) -> str:
    spec = STEWARD_QUEUE_RESOLUTION.get(entity_type)
    if spec and spec.get("label"):
        return spec["label"]
    return entity_type


def decorate_group(entity_type: str, candidate_count: int, job_count: int, row_count: int) -> dict[str, Any]:
    covered = entity_type in STEWARD_QUEUE_RESOLUTION
    return {
        "entity_type": entity_type,
        "label": resolution_label(entity_type),
        "candidate_count": int(candidate_count),
        "job_count": int(job_count),
        "row_count": int(row_count),
        "covered": covered,
    }


def decorate_item(row: dict[str, Any]) -> dict[str, Any]:
    et = str(row["entity_type"])
    job_id = int(row["import_job_id"])
    href = resolution_href(et, job_id)
    return {
        "id": int(row["id"]),
        "entity_type": et,
        "label": resolution_label(et),
        "normalized_key": row["normalized_key"],
        "row_count": int(row["row_count"] or 0),
        "total_units": float(row["total_units"]) if row["total_units"] is not None else None,
        "status": row["status"],
        "import_job_id": job_id,
        "template_slug": row["template_slug"],
        "file_name": row["file_name"],
        "job_status": row["job_status"],
        "steward_href": href,
        "covered": href is not None,
    }


async def steward_failure_queue(
    db: AsyncSession,
    user: dict | None,
    *,
    entity_type: str | None = None,
    limit: int = DEFAULT_ITEM_LIMIT,
) -> dict[str, Any]:
    tenant = tenant_id_from_user(user)
    dbname = (await db.execute(text("SELECT current_database()"))).scalar()
    lim = max(1, min(int(limit), MAX_ITEM_LIMIT))
    et_filter = (entity_type or "").strip() or None

    groups_rows = (
        await db.execute(
            text(
                """
                SELECT
                  c.entity_type,
                  count(1) AS candidate_count,
                  count(DISTINCT c.import_job_id) AS job_count,
                  coalesce(sum(c.row_count), 0) AS row_count
                FROM import_entity_mapping_candidate c
                JOIN import_job j ON j.id = c.import_job_id
                WHERE c.status = :open_status
                  AND j.tenant_id = :tenant
                GROUP BY c.entity_type
                ORDER BY count(1) DESC, c.entity_type
                """
            ),
            {"open_status": OPEN_CANDIDATE_STATUS, "tenant": tenant},
        )
    ).mappings().all()

    groups = [
        decorate_group(
            str(r["entity_type"]),
            int(r["candidate_count"] or 0),
            int(r["job_count"] or 0),
            int(r["row_count"] or 0),
        )
        for r in groups_rows
    ]

    distinct_jobs = int(
        (
            await db.execute(
                text(
                    """
                    SELECT count(DISTINCT c.import_job_id)
                    FROM import_entity_mapping_candidate c
                    JOIN import_job j ON j.id = c.import_job_id
                    WHERE c.status = :open_status
                      AND j.tenant_id = :tenant
                    """
                ),
                {"open_status": OPEN_CANDIDATE_STATUS, "tenant": tenant},
            )
        ).scalar()
        or 0
    )

    items_rows = (
        await db.execute(
            text(
                """
                SELECT
                  c.id,
                  c.entity_type,
                  c.normalized_key,
                  c.row_count,
                  c.total_units,
                  c.status,
                  c.import_job_id,
                  j.template_slug,
                  j.file_name,
                  j.status AS job_status
                FROM import_entity_mapping_candidate c
                JOIN import_job j ON j.id = c.import_job_id
                WHERE c.status = :open_status
                  AND j.tenant_id = :tenant
                  AND (CAST(:entity_type AS VARCHAR) IS NULL OR c.entity_type = CAST(:entity_type AS VARCHAR))
                ORDER BY c.row_count DESC, c.id
                LIMIT :lim
                """
            ),
            {
                "open_status": OPEN_CANDIDATE_STATUS,
                "tenant": tenant,
                "entity_type": et_filter,
                "lim": lim,
            },
        )
    ).mappings().all()

    items = [decorate_item(dict(r)) for r in items_rows]
    total_candidates = sum(g["candidate_count"] for g in groups)
    return {
        "database": dbname,
        "tenant_id": tenant,
        "open_status": OPEN_CANDIDATE_STATUS,
        "groups": groups,
        "items": items,
        "total_candidates": total_candidates,
        "distinct_jobs": distinct_jobs,
        "returned": len(items),
        "truncated": len(items) >= lim and total_candidates > len(items),
        "entity_type_filter": et_filter,
    }
