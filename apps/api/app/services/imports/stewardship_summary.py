"""Read-only Data & Stewardship headline grains. Callers must print current_database() first."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user

# ISO Monday in Africa/Johannesburg — same grain as Movement week keys.
_ISO_WEEK_START_SAST = """
((now() AT TIME ZONE 'Africa/Johannesburg')::date
 - EXTRACT(ISODOW FROM (now() AT TIME ZONE 'Africa/Johannesburg')::date)::int
 + 1)
"""


async def stewardship_summary(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    tenant = tenant_id_from_user(user)
    dbname = (await db.execute(text("SELECT current_database()"))).scalar()
    row = (
        await db.execute(
            text(
                f"""
                SELECT
                  :tenant AS tenant_id,
                  count(*) FILTER (
                    WHERE (created_at AT TIME ZONE 'Africa/Johannesburg')::date >= {_ISO_WEEK_START_SAST}
                  ) AS jobs_iso_week,
                  count(*) FILTER (WHERE created_at >= now() - interval '7 days') AS jobs_last_7d,
                  count(*) FILTER (
                    WHERE status = 'failed' AND created_at >= now() - interval '7 days'
                  ) AS failed_7d,
                  count(*) FILTER (WHERE status = 'failed') AS failed_all,
                  count(*) FILTER (
                    WHERE status = 'completed' AND created_at >= now() - interval '7 days'
                  ) AS completed_7d,
                  count(*) FILTER (WHERE status = 'completed') AS completed_all,
                  count(*) FILTER (WHERE status = 'pending') AS pending_all,
                  count(*) FILTER (
                    WHERE status = 'pending' AND created_at >= now() - interval '7 days'
                  ) AS pending_7d,
                  count(*) FILTER (WHERE archived_at IS NULL) AS jobs_unarchived
                FROM import_job
                WHERE tenant_id = :tenant
                """
            ),
            {"tenant": tenant},
        )
    ).mappings().one()

    templates = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE enabled IS TRUE) AS enabled,
                  count(*) FILTER (
                    WHERE enabled IS TRUE AND hidden IS FALSE AND admin_only IS FALSE
                  ) AS visible_non_admin
                FROM import_template
                """
            )
        )
    ).mappings().one()

    queue_legacy = int(
        (
            await db.execute(
                text(
                    """
                    SELECT count(*) FROM entity_mapping_queue
                    WHERE status NOT IN ('resolved', 'approved', 'ignored')
                    """
                )
            )
        ).scalar()
        or 0
    )
    candidates = (
        await db.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE status = 'needs_review') AS needs_review,
                  count(*) FILTER (
                    WHERE status = 'needs_review'
                      AND entity_type IN ('customer_dealer_token', 'shipment_customer_token', 'cst_location_token')
                  ) AS customerish,
                  count(*) FILTER (
                    WHERE status = 'needs_review'
                      AND entity_type IN ('product_identifier', 'cst_product_token')
                  ) AS productish,
                  count(*) FILTER (
                    WHERE status = 'needs_review'
                      AND entity_type IN ('distributor_token', 'shipment_distributor')
                  ) AS distributorish
                FROM import_entity_mapping_candidate
                """
            )
        )
    ).mappings().one()

    masters = (
        await db.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM dim_product WHERE tenant_id = :tenant) AS products,
                  (SELECT count(*) FROM dim_customer WHERE tenant_id = :tenant) AS customers,
                  (SELECT count(*) FROM dim_customer
                     WHERE tenant_id = :tenant AND customer_status = 'unverified') AS customers_unverified,
                  (SELECT count(*) FROM dim_distributor WHERE tenant_id = :tenant) AS distributors,
                  (SELECT count(*) FROM dim_distributor
                     WHERE tenant_id = :tenant AND distributor_status = 'unverified') AS distributors_unverified,
                  (SELECT count(*) FROM customer_location WHERE location_type = 'store') AS stores
                """
            ),
            {"tenant": tenant},
        )
    ).mappings().one()

    audit_n = int(
        (
            await db.execute(
                text("SELECT count(*) FROM steward_audit_event WHERE tenant_id = :tenant"),
                {"tenant": tenant},
            )
        ).scalar()
        or 0
    )

    jobs_iso = int(row["jobs_iso_week"] or 0)
    jobs_7d = int(row["jobs_last_7d"] or 0)
    failed_7d = int(row["failed_7d"] or 0)
    pending_7d = int(row["pending_7d"] or 0)
    completed_7d = int(row["completed_7d"] or 0)
    pending_all = int(row["pending_all"] or 0)
    failed_all = int(row["failed_all"] or 0)

    return {
        "database": dbname,
        "tenant_id": tenant,
        "jobs_last_7d": jobs_7d,
        "jobs_iso_week": jobs_iso,
        "failed_7d": failed_7d,
        "failed_all": failed_all,
        "completed_7d": completed_7d,
        "completed_all": int(row["completed_all"] or 0),
        "pending_7d": pending_7d,
        "pending_all": pending_all,
        "jobs_unarchived": int(row["jobs_unarchived"] or 0),
        "templates_enabled": int(templates["enabled"] or 0),
        "templates_visible_non_admin": int(templates["visible_non_admin"] or 0),
        "legacy_queue_open": queue_legacy,
        "candidates_needs_review": int(candidates["needs_review"] or 0),
        "candidates_customerish": int(candidates["customerish"] or 0),
        "candidates_productish": int(candidates["productish"] or 0),
        "candidates_distributorish": int(candidates["distributorish"] or 0),
        "products": int(masters["products"] or 0),
        "customers": int(masters["customers"] or 0),
        "customers_unverified": int(masters["customers_unverified"] or 0),
        "distributors": int(masters["distributors"] or 0),
        "distributors_unverified": int(masters["distributors_unverified"] or 0),
        "stores": int(masters["stores"] or 0),
        "audit_events": audit_n,
        "labels": {
            "jobs_last_7d": "Jobs in last 7 days",
            "jobs_iso_week": "Jobs this ISO week",
            "failed_7d": "Failed (last 7 days)",
            "pending_7d": "Pending mapping (last 7 days)",
            "completed_7d": "Completed (last 7 days)",
            "templates_enabled": "Enabled import types",
            "legacy_queue_open": "Legacy mapping-queue rows",
            "products": "Products",
            "customers": "Customers / dealers",
            "distributors": "Distributors",
            "stores": "Stores",
            "customers_unverified": "Unverified customers",
            "distributors_unverified": "Unverified distributors",
        },
        "captions": {
            "jobs_last_7d": f"ISO week-to-date is {jobs_iso} after Monday 00:00 SAST",
            "failed_7d": "status = failed; not validation_failed",
            "pending_7d": f"{pending_all} older jobs still pending mapping",
            "completed_7d": "status = completed — production has no applied status",
            "templates_enabled": f"{int(templates['visible_non_admin'] or 0)} visible to non-admin",
            "legacy_queue_open": (
                f"{int(candidates['needs_review'] or 0)} per-job candidates still need_review; "
                "cross-job queue is D-0002"
            ),
            "stores": "customer_location where location_type = store — no store master grid",
            "customers_unverified": "customer_status = unverified; not a lab fixture",
            "distributors_unverified": "distributor_status = unverified",
        },
    }
