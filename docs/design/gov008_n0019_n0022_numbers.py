"""GOV-008 independent NUMBER RULE re-exec for N-0019..N-0022. Read-only.

Prints current_database() first. Does not write. Run from apps/api:

  .venv\\Scripts\\python.exe ..\\..\\docs\\design\\gov008_n0019_n0022_numbers.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

TENANT = "default"


def main() -> None:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as c:
        dbname = c.execute(text("SELECT current_database()")).scalar()
        print(f"current_database()={dbname}")
        if dbname != "cip":
            print("STOP: not cip; no further queries")
            return

        print("\n=== N-0019 Overview ===")
        dash = c.execute(
            text(
                """
                SELECT count(*)::int AS dashboards
                FROM dashboard
                WHERE tenant_id = :t
                """
            ),
            {"t": TENANT},
        ).mappings().one()
        widgets = c.execute(
            text(
                """
                SELECT count(*)::int AS widgets
                FROM dashboard_widget w
                JOIN dashboard d ON d.id = w.dashboard_id
                WHERE d.tenant_id = :t
                """
            ),
            {"t": TENANT},
        ).mappings().one()
        reports = c.execute(
            text(
                """
                SELECT count(*)::int AS reports
                FROM saved_report
                WHERE tenant_id = :t
                """
            ),
            {"t": TENANT},
        ).mappings().one()
        print(f"dashboards={dash['dashboards']} widgets={widgets['widgets']} saved_reports={reports['reports']}")

        print("\n=== N-0020 Planning ===")
        cases = c.execute(
            text(
                """
                SELECT count(*)::int
                FROM commercial_lineup_case
                WHERE superseded_by_case_id IS NULL
                  AND commercial_status NOT IN ('cancelled', 'superseded')
                """
            )
        ).scalar()
        line_row = c.execute(
            text(
                """
                SELECT
                  count(*)::int AS lines,
                  coalesce(sum(l.quantity_units), 0) AS plan_units
                FROM commercial_lineup_line l
                JOIN commercial_lineup_case c ON c.id = l.case_id
                WHERE c.superseded_by_case_id IS NULL
                  AND c.commercial_status NOT IN ('cancelled', 'superseded')
                  AND l.row_status IS DISTINCT FROM 'superseded'
                """
            )
        ).mappings().one()
        not_ready = c.execute(
            text(
                """
                SELECT count(*)::int
                FROM commercial_lineup_line l
                JOIN commercial_lineup_case c ON c.id = l.case_id
                LEFT JOIN commercial_sku_assumption sa ON sa.product_id = l.product_id
                LEFT JOIN commercial_customer_term ct ON ct.customer_id = l.customer_id
                WHERE c.superseded_by_case_id IS NULL
                  AND c.commercial_status NOT IN ('cancelled', 'superseded')
                  AND l.row_status IS DISTINCT FROM 'superseded'
                  AND (
                    l.product_id IS NULL OR sa.product_id IS NULL
                    OR l.customer_id IS NULL OR ct.customer_id IS NULL
                    OR l.distributor_id IS NULL
                    OR sa.controlled_cost_amount IS NULL
                    OR sa.controlled_cost_amount <= 0
                  )
                """
            )
        ).scalar()
        econ = c.execute(
            text(
                """
                SELECT
                  count(*)::int AS plan_lines,
                  count(*) FILTER (
                    WHERE calc_flags IS NOT NULL
                      AND jsonb_typeof(calc_flags) = 'array'
                      AND jsonb_array_length(calc_flags) > 0
                  )::int AS flagged
                FROM commercial_plan_line
                """
            )
        ).mappings().one()
        print(
            f"cases={cases} lines={line_row['lines']} plan_units={line_row['plan_units']} "
            f"not_ready={not_ready} plan_lines={econ['plan_lines']} flagged={econ['flagged']}"
        )

        print("\n=== N-0021 Administration ===")
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)
        since_7d = now - timedelta(days=7)
        users = c.execute(
            text(
                """
                SELECT role, count(*)::int AS n
                FROM app_user
                WHERE tenant_id = :t AND is_active IS TRUE
                GROUP BY role
                """
            ),
            {"t": TENANT},
        ).mappings().all()
        jobs = c.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE status = 'running')::int AS running,
                  count(*) FILTER (WHERE status = 'pending')::int AS pending,
                  count(*) FILTER (WHERE status = 'failed')::int AS failed_open,
                  count(*) FILTER (
                    WHERE status = 'failed'
                      AND coalesce(completed_at, updated_at, created_at) >= :since_24h
                  )::int AS failed_24h
                FROM import_job
                WHERE tenant_id = :t AND archived_at IS NULL
                """
            ),
            {"t": TENANT, "since_24h": since_24h},
        ).mappings().one()
        sql_n = c.execute(
            text(
                """
                SELECT
                  count(*) FILTER (WHERE created_at >= :since_7d)::int AS sql_7d,
                  count(*)::int AS sql_all
                FROM sql_viewer_audit
                WHERE tenant_id = :t
                """
            ),
            {"t": TENANT, "since_7d": since_7d},
        ).mappings().one()
        print("users_by_role=" + ", ".join(f"{r['role']}={r['n']}" for r in users))
        print(
            f"running={jobs['running']} pending={jobs['pending']} "
            f"failed_open={jobs['failed_open']} failed_24h={jobs['failed_24h']} "
            f"sql_7d={sql_n['sql_7d']} sql_all={sql_n['sql_all']}"
        )

        print("\n=== N-0022 Stock leftover leaves ===")
        bounds = c.execute(
            text(
                """
                WITH bounds AS (
                  SELECT
                    (now() AT TIME ZONE 'Africa/Johannesburg')::date AS today_sast,
                    (
                      (now() AT TIME ZONE 'Africa/Johannesburg')::date
                      - (EXTRACT(ISODOW FROM (now() AT TIME ZONE 'Africa/Johannesburg')::date)::int - 1)
                    )::date AS week_monday
                )
                SELECT
                  b.today_sast,
                  to_char(b.today_sast, 'IYYY-"W"IW') AS current_iso_week,
                  (
                    SELECT count(*)::int
                    FROM fact_customer_sellthrough s
                    WHERE s.tenant_id = :t
                      AND s.period_start_date >= b.week_monday
                      AND s.period_start_date < b.week_monday + 7
                  ) AS cst_current_week_rows,
                  (SELECT max(s.period_start_date) FROM fact_customer_sellthrough s WHERE s.tenant_id = :t) AS cst_max_period,
                  (SELECT to_char(max(s.period_start_date), 'IYYY-"W"IW') FROM fact_customer_sellthrough s WHERE s.tenant_id = :t) AS cst_max_iso_week,
                  (
                    SELECT count(*)::int
                    FROM fact_customer_sellthrough s
                    WHERE s.tenant_id = :t
                      AND s.period_start_date = (
                        SELECT max(s2.period_start_date) FROM fact_customer_sellthrough s2 WHERE s2.tenant_id = :t
                      )
                  ) AS cst_max_period_rows,
                  (
                    SELECT count(*)::int FROM (
                      SELECT DISTINCT (
                        so.transaction_date - (EXTRACT(ISODOW FROM so.transaction_date)::int - 1)
                      ) AS week_monday
                      FROM fact_sales_sellout so
                      WHERE so.tenant_id = :t
                        AND so.transaction_date >= b.week_monday - 49
                        AND so.transaction_date < b.week_monday + 7
                    ) w
                  ) AS sellout_trailing_weeks,
                  (SELECT max(so.transaction_date) FROM fact_sales_sellout so WHERE so.tenant_id = :t) AS sellout_max_tx,
                  (SELECT to_char(max(so.transaction_date), 'IYYY-"W"IW') FROM fact_sales_sellout so WHERE so.tenant_id = :t) AS sellout_max_iso_week,
                  (SELECT count(*)::int FROM fact_demand_forecast f WHERE f.tenant_id = :t) AS forecast_rows
                FROM bounds b
                """
            ),
            {"t": TENANT},
        ).mappings().one()
        customers = c.execute(
            text(
                """
                SELECT c.name AS name, count(*)::int AS n
                FROM fact_customer_sellthrough s
                JOIN dim_customer c ON c.id = s.customer_id
                WHERE s.tenant_id = :t
                  AND s.period_start_date = (
                    SELECT max(s2.period_start_date) FROM fact_customer_sellthrough s2 WHERE s2.tenant_id = :t
                  )
                GROUP BY c.name
                ORDER BY n DESC
                LIMIT 3
                """
            ),
            {"t": TENANT},
        ).mappings().all()
        print(
            f"today_sast={bounds['today_sast']} week={bounds['current_iso_week']} "
            f"cst_current={bounds['cst_current_week_rows']} "
            f"cst_max={bounds['cst_max_period']} {bounds['cst_max_iso_week']} rows={bounds['cst_max_period_rows']}"
        )
        print("cst_customers=" + ", ".join(f"{r['name']}={r['n']}" for r in customers))
        print(
            f"sellout_trailing={bounds['sellout_trailing_weeks']} "
            f"sellout_max={bounds['sellout_max_tx']} {bounds['sellout_max_iso_week']} "
            f"forecast_rows={bounds['forecast_rows']}"
        )


if __name__ == "__main__":
    main()
