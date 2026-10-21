"""N-0111 repair: READ-ONLY probe part 3 (merge record of 2026-08-08). usage: python probe_unmerge3.py <dbname>"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "PROGRAMME_20261014" / "n0110"))

import psycopg  # noqa: E402

from n0110_numbers import url_for  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "cip"

with psycopg.connect(url_for(DB)) as conn:
    conn.read_only = True

    def q(sql, *a):
        try:
            return conn.execute(sql, a).fetchall()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            return [("ERR", str(exc)[:300])]

    print("current_database()", q("select current_database()")[0][0], "(read-only)")
    notes = q("select coalesce(notes_summary,'') from dim_customer where id = 1")[0][0]
    print("OPEN_CHANNEL notes_summary (len %d):" % len(notes))
    print(notes)
    print("steward_audit_event columns", q(
        "select column_name from information_schema.columns where table_name = 'steward_audit_event' order by ordinal_position"))
    print("steward_audit_event naming 1152/4145", q(
        "select * from steward_audit_event where cast(row_to_json(steward_audit_event) as text) like '%%1152%%' "
        "or cast(row_to_json(steward_audit_event) as text) like '%%4145%%' order by 1 limit 20"))
    print("steward_audit_event 2026-08-08", q(
        "select * from steward_audit_event where created_at >= '2026-08-08' and created_at < '2026-08-09' order by 1 limit 20"))
    print("alias updated_at for revoked compuspeed/syntech", q(
        "select id, raw_token, status, created_at, updated_at from customer_source_token_alias where id in (1406, 4400, 4740, 5439)"))
    print("DSI staging on OC compuspeed/syntech by job", q(
        "select import_job_id, raw_customer_dealer_token, count(*), count(fact_sellout_row_id), count(fact_inventory_row_id) "
        "from import_distributor_si_staging_line where resolved_customer_id = 1 and (raw_customer_dealer_token ilike '%%compuspeed%%' "
        "or raw_customer_dealer_token ilike '%%syntech%%') group by 1, 2 order by 1, 2"))
    print("sellout facts on OC by staging token", q(
        "select coalesce(s.raw_customer_dealer_token, '(no staging line)'), count(*), sum(f.units) from fact_sales_sellout f "
        "left join import_distributor_si_staging_line s on s.id = f.staging_line_id where f.customer_id = 1 group by 1 order by 1"))
    print("other OC rows from DSI staging lines (inventory recon / velocity / returns)", q(
        "select 'recon', count(*) from fact_inventory_reconciliation where customer_id = 1 union all "
        "select 'velocity', count(*) from fact_customer_velocity where customer_id = 1 union all "
        "select 'returns', count(*) from fact_returns where customer_id = 1"))
