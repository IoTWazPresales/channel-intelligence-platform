"""N-0111 repair 2: READ-ONLY. Why do the 298 unreported-weeks positions stay unreported after the bridge rule?
usage (via dbrun.py): python probe_restarts.py cip"""

from __future__ import annotations

import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402

with SessionLocal() as s:
    db = s.execute(text("select current_database()")).scalar()
    print("current_database()", db, "(read-only)")
    if len(sys.argv) < 2 or sys.argv[1] != db:
        raise SystemExit("pass the database name")
    s.execute(text("SET TRANSACTION READ ONLY"))

    print("restart rows by customer:", s.execute(text(
        "select c.name, count(*), min(p.period_start_date - p.previous_period_end_date), "
        "percentile_cont(0.5) within group (order by p.period_start_date - p.previous_period_end_date), "
        "max(p.period_start_date - p.previous_period_end_date) "
        "from customer_stock_position p join dim_customer c on c.id = p.customer_id "
        "where p.status = 'chain_restart' group by 1 order by 2 desc")).all())

    # for each restart row: reported fact rows (any figure) strictly between previous end and this start
    rows = s.execute(text("""
        with r as (
          select p.customer_id, p.product_id, p.previous_period_end_date as pe, p.period_start_date as st
          from customer_stock_position p where p.status = 'chain_restart')
        select count(*) as restarts,
               count(*) filter (where n.rows_between = 0) as no_row_at_all,
               count(*) filter (where n.rows_between > 0 and n.rows_with_units = 0) as rows_but_no_units,
               count(*) filter (where n.rows_with_units > 0) as some_units,
               count(*) filter (where (r.st - r.pe) <= 8) as gap_le_8_days
        from r cross join lateral (
          select count(*) as rows_between,
                 count(*) filter (where f.units_sold is not null
                                  and (f.figure_import_jobs = '{}'::jsonb or f.figure_import_jobs ? 'units_sold')) as rows_with_units
          from fact_customer_sellthrough f
          where f.customer_id = r.customer_id and f.product_id = r.product_id
            and f.period_start_date > r.pe and f.period_start_date < r.st) n
        """)).first()
    print("restarts, rows between (all grains) -> (restarts, no_row_at_all, rows_but_no_units, some_units, gap<=8d):", tuple(rows))

    print("sample restart rows (customer, product, prev_end, start, days, fact rows between):")
    for r in s.execute(text("""
        select c.name, p.product_id, p.previous_period_end_date, p.period_start_date,
               p.period_start_date - p.previous_period_end_date as days,
               (select count(*) from fact_customer_sellthrough f where f.customer_id = p.customer_id
                  and f.product_id = p.product_id and f.period_start_date > p.previous_period_end_date
                  and f.period_start_date < p.period_start_date) as between_rows
        from customer_stock_position p join dim_customer c on c.id = p.customer_id
        where p.status = 'chain_restart' order by c.name, p.period_start_date limit 12""")).all():
        print("  ", tuple(r))

    print("fact rows by customer: total / with on-hand / without on-hand / without on-hand and units>0 / no units provenance:")
    for r in s.execute(text("""
        select c.name, count(*), count(f.reported_soh), count(*) filter (where f.reported_soh is null),
               count(*) filter (where f.reported_soh is null and f.units_sold > 0),
               count(*) filter (where f.reported_soh is null and f.figure_import_jobs <> '{}'::jsonb
                                and not (f.figure_import_jobs ? 'units_sold'))
        from fact_customer_sellthrough f join dim_customer c on c.id = f.customer_id
        group by 1 order by 2 desc""")).all():
        print("  ", tuple(r))
    s.rollback()
