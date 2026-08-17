"""Weeks-of-cover observation persist — set-based reconstruct + apply-time decision rows.

BACKLOG-097. Derived series, not a fact. Same SQL is the product path (apply) and
the ops replay (097-D). Never loop dates × pairs in Python.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.channel_ops_config import REPLENISHMENT_WOC_THRESHOLD_WEEKS
from app.services.channel_ops_derived_stock import VELOCITY_NEAR_ZERO, VELOCITY_WINDOW_DAYS
from app.services.commercial_tenant_profile import (
    reporting_cadence,
    reporting_today,
    woc_min_velocity_days,
)

logger = logging.getLogger(__name__)

FORMULA_VERSION = "A3-02.v1"
WOC_TRIGGER_DSI_APPLY = "dsi_apply"
WOC_TRIGGER_SHIPMENT_APPLY = "shipment_apply"
WOC_TRIGGER_AS_OF_BACKFILL = "as_of_backfill"

SourceKeyKind = Literal["job", "asof"]

_CADENCE_WEEKDAY: dict[str, int] = {
    "weekly_monday": 0,
    "weekly_tuesday": 1,
    "weekly_wednesday": 2,
    "weekly_thursday": 3,
    "weekly_friday": 4,
    "weekly_saturday": 5,
    "weekly_sunday": 6,
}

_CADENCE_INTERVAL: dict[str, str] = {
    "daily": "1 day",
    "weekly_monday": "7 days",
    "weekly_tuesday": "7 days",
    "weekly_wednesday": "7 days",
    "weekly_thursday": "7 days",
    "weekly_friday": "7 days",
    "weekly_saturday": "7 days",
    "weekly_sunday": "7 days",
}

# Historic reconstruct can be heavy; fail into the retryable marker rather than hang apply.
_RECONSTRUCT_STATEMENT_TIMEOUT_MS = 180_000

_UPSERT_SQL = """
INSERT INTO weeks_of_cover_observation (
    tenant_id,
    distributor_id,
    product_id,
    snapshot_date,
    cover_as_of_date,
    observed_at,
    import_job_id,
    trigger,
    reported_soh,
    sell_out_since,
    landed_since,
    derived_stock,
    weekly_velocity,
    weeks_of_cover,
    replenishment_flag,
    replenishment_threshold_weeks,
    params,
    formula_version,
    data_vintage,
    source_key,
    created_at,
    updated_at
)
WITH spine AS (
    SELECT generate_series(
        CAST(:spine_start AS date),
        CAST(:as_of AS date),
        CAST(:cadence_interval AS interval)
    )::date AS cover_as_of_date
),
snap_raw AS (
    SELECT DISTINCT ON (inv.product_id, inv.as_of_date)
        inv.product_id,
        inv.as_of_date,
        inv.on_hand_units
    FROM fact_inventory_distributor inv
    WHERE inv.distributor_id = CAST(:distributor_id AS integer)
      AND inv.tenant_id = CAST(:tenant_id AS text)
      AND inv.as_of_date <= CAST(:as_of AS date)
    ORDER BY inv.product_id, inv.as_of_date, inv.id DESC
),
snap_intervals AS (
    SELECT
        product_id,
        as_of_date AS snapshot_date,
        on_hand_units AS reported_soh,
        LEAD(as_of_date) OVER (PARTITION BY product_id ORDER BY as_of_date) AS next_snapshot_date
    FROM snap_raw
),
spine_snap AS (
    SELECT
        s.cover_as_of_date,
        si.product_id,
        si.snapshot_date,
        si.reported_soh
    FROM spine s
    JOIN snap_intervals si
      ON si.snapshot_date <= s.cover_as_of_date
     AND (si.next_snapshot_date IS NULL OR s.cover_as_of_date < si.next_snapshot_date)
),
first_obs AS (
    SELECT product_id, MIN(first_d) AS first_observation_date
    FROM (
        SELECT product_id, MIN(as_of_date) AS first_d
        FROM fact_inventory_distributor
        WHERE distributor_id = CAST(:distributor_id AS integer)
          AND tenant_id = CAST(:tenant_id AS text)
        GROUP BY product_id
        UNION ALL
        SELECT product_id, MIN(transaction_date) AS first_d
        FROM fact_sales_sellout
        WHERE distributor_id = CAST(:distributor_id AS integer)
          AND tenant_id = CAST(:tenant_id AS text)
          AND product_id IS NOT NULL
        GROUP BY product_id
    ) origins
    GROUP BY product_id
),
sell_since AS (
    SELECT
        sp.product_id,
        sp.cover_as_of_date,
        COALESCE(SUM(ss.units), 0) AS sell_out_since
    FROM spine_snap sp
    LEFT JOIN fact_sales_sellout ss
      ON ss.distributor_id = CAST(:distributor_id AS integer)
     AND ss.product_id = sp.product_id
     AND ss.transaction_date > sp.snapshot_date
     AND ss.transaction_date <= sp.cover_as_of_date
    GROUP BY sp.product_id, sp.cover_as_of_date
),
land_since AS (
    SELECT
        sp.product_id,
        sp.cover_as_of_date,
        COALESCE(SUM(sh.quantity), 0) AS landed_since
    FROM spine_snap sp
    LEFT JOIN fact_inbound_shipment sh
      ON sh.distributor_id = CAST(:distributor_id AS integer)
     AND sh.product_id = sp.product_id
     AND sh.pod_date IS NOT NULL
     AND sh.pod_date > sp.snapshot_date
     AND sh.pod_date <= sp.cover_as_of_date
     AND lower(sh.line_state) = 'shipped'
    GROUP BY sp.product_id, sp.cover_as_of_date
),
vel AS (
    SELECT
        sp.product_id,
        sp.cover_as_of_date,
        COALESCE(SUM(ss.units), 0) AS vel_units,
        GREATEST(
            1,
            (
                sp.cover_as_of_date
                - GREATEST(
                    sp.cover_as_of_date - CAST(:velocity_window_days AS integer),
                    fo.first_observation_date
                )
            )
        ) AS days_used
    FROM spine_snap sp
    JOIN first_obs fo ON fo.product_id = sp.product_id
    LEFT JOIN fact_sales_sellout ss
      ON ss.distributor_id = CAST(:distributor_id AS integer)
     AND ss.product_id = sp.product_id
     AND ss.transaction_date > (sp.cover_as_of_date - CAST(:velocity_window_days AS integer))
     AND ss.transaction_date <= sp.cover_as_of_date
    GROUP BY sp.product_id, sp.cover_as_of_date, fo.first_observation_date
),
computed AS (
    SELECT
        sp.cover_as_of_date,
        sp.product_id,
        sp.snapshot_date,
        CAST(sp.reported_soh AS numeric) AS reported_soh,
        CAST(COALESCE(se.sell_out_since, 0) AS numeric) AS sell_out_since,
        CAST(COALESCE(ls.landed_since, 0) AS numeric) AS landed_since,
        CAST(sp.reported_soh AS numeric)
            - CAST(COALESCE(se.sell_out_since, 0) AS numeric)
            + CAST(COALESCE(ls.landed_since, 0) AS numeric) AS derived_stock,
        v.days_used,
        CASE
            WHEN v.days_used >= CAST(:velocity_window_days AS integer)
                THEN CAST(COALESCE(v.vel_units, 0) AS numeric) / 52
            ELSE CAST(COALESCE(v.vel_units, 0) AS numeric) * 7 / v.days_used
        END AS weekly_velocity,
        (v.days_used < CAST(:min_vel_days AS integer)) AS insufficient_history,
        (v.days_used >= CAST(:velocity_window_days AS integer)) AS mature_window
    FROM spine_snap sp
    LEFT JOIN sell_since se
      ON se.product_id = sp.product_id AND se.cover_as_of_date = sp.cover_as_of_date
    LEFT JOIN land_since ls
      ON ls.product_id = sp.product_id AND ls.cover_as_of_date = sp.cover_as_of_date
    LEFT JOIN vel v
      ON v.product_id = sp.product_id AND v.cover_as_of_date = sp.cover_as_of_date
)
SELECT
    CAST(:tenant_id AS text),
    CAST(:distributor_id AS integer),
    c.product_id,
    c.snapshot_date,
    c.cover_as_of_date,
    CAST(:observed_at AS timestamptz),
    CAST(:import_job_id AS integer),
    CAST(:trigger AS text),
    c.reported_soh,
    c.sell_out_since,
    c.landed_since,
    c.derived_stock,
    CASE WHEN c.insufficient_history THEN NULL ELSE c.weekly_velocity END,
    CASE
        WHEN c.insufficient_history THEN NULL
        WHEN c.weekly_velocity IS NULL THEN NULL
        WHEN c.weekly_velocity <= CAST(:velocity_near_zero AS numeric) THEN NULL
        ELSE c.derived_stock / c.weekly_velocity
    END,
    CASE
        WHEN c.insufficient_history THEN FALSE
        WHEN c.weekly_velocity IS NULL OR c.weekly_velocity <= CAST(:velocity_near_zero AS numeric) THEN FALSE
        WHEN (c.derived_stock / c.weekly_velocity) > 0
         AND (c.derived_stock / c.weekly_velocity) < CAST(:threshold_weeks AS numeric) THEN TRUE
        ELSE FALSE
    END,
    CAST(:threshold_weeks AS numeric),
    jsonb_build_object(
        'reconstructed_from_current_facts', CAST(:reconstructed AS boolean),
        'reporting_cadence', CAST(:cadence AS text),
        'velocity_method', CASE
            WHEN c.mature_window THEN 'a3_02_364_over_52'
            ELSE 'available_window_over_weeks'
        END,
        'velocity_window_days_used', c.days_used,
        'velocity_days_available', c.days_used,
        'velocity_window_days', CAST(:velocity_window_days AS integer),
        'insufficient_velocity_history', c.insufficient_history,
        'reason', CASE
            WHEN c.insufficient_history THEN 'insufficient_velocity_history'
            WHEN c.weekly_velocity IS NULL OR c.weekly_velocity <= CAST(:velocity_near_zero AS numeric)
                THEN 'velocity_near_zero'
            ELSE NULL
        END,
        'file_period_end', CAST(:file_period_end AS date),
        'triggered_by_job_id', CAST(:triggered_by_job_id AS integer)
    ),
    CAST(:formula_version AS text),
    jsonb_build_object(
        'computed_through', CAST(:as_of AS date),
        'grain', 'distributor_x_product',
        'trigger', CAST(:trigger AS text)
    ),
    CASE
        WHEN CAST(:source_key_kind AS text) = 'job'
            THEN 'woc:' || CAST(:distributor_id AS integer)::text
                 || ':' || c.product_id::text
                 || ':job:' || CAST(:import_job_id AS integer)::text
        ELSE 'woc:' || CAST(:distributor_id AS integer)::text
             || ':' || c.product_id::text
             || ':asof:' || to_char(c.cover_as_of_date, 'YYYY-MM-DD')
    END,
    now(),
    now()
FROM computed c
ON CONFLICT (source_key) DO UPDATE SET
    snapshot_date = EXCLUDED.snapshot_date,
    cover_as_of_date = EXCLUDED.cover_as_of_date,
    observed_at = EXCLUDED.observed_at,
    import_job_id = EXCLUDED.import_job_id,
    trigger = EXCLUDED.trigger,
    reported_soh = EXCLUDED.reported_soh,
    sell_out_since = EXCLUDED.sell_out_since,
    landed_since = EXCLUDED.landed_since,
    derived_stock = EXCLUDED.derived_stock,
    weekly_velocity = EXCLUDED.weekly_velocity,
    weeks_of_cover = EXCLUDED.weeks_of_cover,
    replenishment_flag = EXCLUDED.replenishment_flag,
    replenishment_threshold_weeks = EXCLUDED.replenishment_threshold_weeks,
    params = EXCLUDED.params,
    formula_version = EXCLUDED.formula_version,
    data_vintage = EXCLUDED.data_vintage,
    updated_at = now()
"""


def woc_observation_source_key_job(*, distributor_id: int, product_id: int, import_job_id: int) -> str:
    return f"woc:{int(distributor_id)}:{int(product_id)}:job:{int(import_job_id)}"


def woc_observation_source_key_asof(*, distributor_id: int, product_id: int, cover_as_of: date) -> str:
    return f"woc:{int(distributor_id)}:{int(product_id)}:asof:{cover_as_of.isoformat()}"


def align_spine_start(floor: date, cadence: str) -> date:
    if cadence == "daily":
        return floor
    target = _CADENCE_WEEKDAY.get(cadence)
    if target is None:
        target = 0
    delta = (target - floor.weekday()) % 7
    return floor + timedelta(days=delta)


def cadence_interval_sql(cadence: str) -> str:
    return _CADENCE_INTERVAL.get(cadence, "7 days")


def table_exists(session: Session, table_name: str = "weeks_of_cover_observation") -> bool:
    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def distributor_inventory_floor(
    session: Session,
    *,
    tenant_id: str,
    distributor_id: int,
) -> date | None:
    row = session.execute(
        text(
            """
            SELECT MIN(as_of_date)
            FROM fact_inventory_distributor
            WHERE tenant_id = CAST(:tenant_id AS text)
              AND distributor_id = CAST(:distributor_id AS integer)
            """
        ),
        {"tenant_id": tenant_id, "distributor_id": int(distributor_id)},
    ).scalar()
    return row if isinstance(row, date) else None


def _upsert(
    session: Session,
    *,
    tenant_id: str,
    distributor_id: int,
    as_of: date,
    spine_start: date,
    cadence: str,
    trigger: str,
    source_key_kind: SourceKeyKind,
    import_job_id: int | None,
    reconstructed: bool,
    file_period_end: date | None,
    min_vel_days: int,
    threshold_weeks: float,
) -> int:
    if spine_start > as_of:
        return 0
    timeout_ms = int(_RECONSTRUCT_STATEMENT_TIMEOUT_MS)
    session.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
    params = {
        "tenant_id": tenant_id,
        "distributor_id": int(distributor_id),
        "as_of": as_of,
        "spine_start": spine_start,
        "cadence_interval": cadence_interval_sql(cadence),
        "cadence": cadence,
        "trigger": trigger,
        "source_key_kind": source_key_kind,
        "import_job_id": int(import_job_id) if import_job_id is not None else None,
        "triggered_by_job_id": int(import_job_id) if import_job_id is not None else None,
        "reconstructed": reconstructed,
        "file_period_end": file_period_end,
        "min_vel_days": int(min_vel_days),
        "threshold_weeks": float(threshold_weeks),
        "velocity_window_days": int(VELOCITY_WINDOW_DAYS),
        "velocity_near_zero": float(VELOCITY_NEAR_ZERO),
        "formula_version": FORMULA_VERSION,
        "observed_at": datetime.now(timezone.utc),
    }
    # SET LOCAL + INSERT must share one connection; SQLAlchemy executes the string as one batch.
    result = session.execute(text(_UPSERT_SQL), params)
    return int(result.rowcount or 0)


def reconstruct_woc_observations(
    session: Session,
    *,
    tenant_id: str,
    distributor_id: int,
    as_of: date | None = None,
    import_job_id: int | None = None,
    trigger: str = WOC_TRIGGER_AS_OF_BACKFILL,
    file_period_end: date | None = None,
) -> dict[str, Any]:
    """Set-based spine reconstruct for one distributor. Idempotent on source_key.

    Product path and ops replay share this function — do not fork it.
    """
    if not table_exists(session):
        return {"ok": False, "skipped": True, "reason": "table_missing", "rows_upserted": 0}

    tid = (tenant_id or "default").strip() or "default"
    cadence = reporting_cadence(tid)
    min_days = woc_min_velocity_days(tid)
    cover_as_of = as_of or reporting_today(tid)
    floor = distributor_inventory_floor(session, tenant_id=tid, distributor_id=int(distributor_id))
    if floor is None:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_inventory_floor",
            "rows_upserted": 0,
            "distributor_id": int(distributor_id),
        }
    spine_start = align_spine_start(floor, cadence)
    threshold = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)
    rows = _upsert(
        session,
        tenant_id=tid,
        distributor_id=int(distributor_id),
        as_of=cover_as_of,
        spine_start=spine_start,
        cadence=cadence,
        trigger=trigger,
        source_key_kind="asof",
        import_job_id=None,
        reconstructed=True,
        file_period_end=file_period_end,
        min_vel_days=min_days,
        threshold_weeks=threshold,
    )
    return {
        "ok": True,
        "skipped": False,
        "rows_upserted": rows,
        "distributor_id": int(distributor_id),
        "spine_start": spine_start.isoformat(),
        "as_of": cover_as_of.isoformat(),
        "cadence": cadence,
        "woc_min_velocity_days": min_days,
        "trigger": trigger,
        "import_job_id": import_job_id,
    }


def persist_apply_decision_observations(
    session: Session,
    *,
    tenant_id: str,
    distributor_id: int,
    import_job_id: int,
    trigger: str,
    cover_as_of: date,
    file_period_end: date | None,
) -> dict[str, Any]:
    """One-date spine for the apply-time decision row (source_key :job:{id})."""
    if not table_exists(session):
        return {"ok": False, "skipped": True, "reason": "table_missing", "rows_upserted": 0}
    if trigger not in {WOC_TRIGGER_DSI_APPLY, WOC_TRIGGER_SHIPMENT_APPLY}:
        raise ValueError(f"invalid apply trigger {trigger!r}")
    tid = (tenant_id or "default").strip() or "default"
    cadence = reporting_cadence(tid)
    min_days = woc_min_velocity_days(tid)
    threshold = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)
    rows = _upsert(
        session,
        tenant_id=tid,
        distributor_id=int(distributor_id),
        as_of=cover_as_of,
        spine_start=cover_as_of,
        cadence="daily",
        trigger=trigger,
        source_key_kind="job",
        import_job_id=int(import_job_id),
        reconstructed=False,
        file_period_end=file_period_end,
        min_vel_days=min_days,
        threshold_weeks=threshold,
    )
    return {
        "ok": True,
        "rows_upserted": rows,
        "distributor_id": int(distributor_id),
        "trigger": trigger,
        "cover_as_of": cover_as_of.isoformat(),
        "cadence_stamped": cadence,
        "import_job_id": int(import_job_id),
    }


def persist_woc_observations_for_distributor(
    session: Session,
    *,
    tenant_id: str,
    distributor_id: int,
    import_job_id: int | None,
    trigger: str,
    file_period_end: date | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Reconstruct through today, then write the apply decision row when triggered by apply."""
    tid = (tenant_id or "default").strip() or "default"
    cover_as_of = as_of or reporting_today(tid)
    reconstructed = reconstruct_woc_observations(
        session,
        tenant_id=tid,
        distributor_id=int(distributor_id),
        as_of=cover_as_of,
        import_job_id=import_job_id,
        file_period_end=file_period_end,
    )
    decision: dict[str, Any] | None = None
    if trigger in {WOC_TRIGGER_DSI_APPLY, WOC_TRIGGER_SHIPMENT_APPLY} and import_job_id is not None:
        decision_date = file_period_end or cover_as_of
        decision = persist_apply_decision_observations(
            session,
            tenant_id=tid,
            distributor_id=int(distributor_id),
            import_job_id=int(import_job_id),
            trigger=trigger,
            cover_as_of=decision_date,
            file_period_end=file_period_end,
        )
    return {
        "ok": bool(reconstructed.get("ok")),
        "reconstruct": reconstructed,
        "decision": decision,
        "distributor_id": int(distributor_id),
    }


def shipment_distributor_ids_for_job(session: Session, job_id: int) -> list[int]:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT distributor_id
            FROM fact_inbound_shipment
            WHERE import_job_id = CAST(:job_id AS integer)
              AND distributor_id IS NOT NULL
            """
        ),
        {"job_id": int(job_id)},
    ).all()
    return [int(r[0]) for r in rows if r[0] is not None]


def mark_woc_reconstruct_on_job(
    session: Session,
    job_id: int,
    payload: dict[str, Any],
) -> None:
    """Retryable marker on import_job.staged_metadata (best-effort isolate)."""
    from sqlalchemy.orm.attributes import flag_modified

    from app.models.ingestion import ImportJob

    job = session.get(ImportJob, int(job_id))
    if job is None:
        return
    meta = dict(job.staged_metadata or {})
    meta["woc_observation"] = payload
    job.staged_metadata = meta
    flag_modified(job, "staged_metadata")
    session.add(job)
