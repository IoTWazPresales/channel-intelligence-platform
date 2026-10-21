"""N-0111 repair: READ-ONLY probe part 2 (records, merge logs, shipment tokens). usage: python probe_unmerge2.py <dbname>"""

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
    for r in q("select id, code, name, customer_status, merged_into_customer_id, left(coalesce(notes_summary,''),300), "
               "created_at, updated_at from dim_customer where id in (1152, 4145) or merged_into_customer_id = 1"):
        print("record", r)
    cols = [c for (c,) in q("select column_name from information_schema.columns where table_name = 'dim_customer' order by ordinal_position")]
    print("dim_customer columns", cols)
    print("merge/log tables", q(
        "select table_name from information_schema.tables where table_schema = 'public' and "
        "(table_name like '%%merge%%' or table_name like '%%audit%%' or table_name like '%%history%%' or table_name like '%%change%%') order by 1"))
    print("platform audit merges", q(
        "select id, created_at, action, target_id, left(cast(detail_json as text), 300) from platform_audit_event "
        "where action ilike '%%merge%%' order by id limit 20"))

    print("shipment_evidence_line on OC by dealer token (top 25)", q(
        "select customer_dealer_token, count(*) from shipment_evidence_line where resolved_customer_id = 1 "
        "group by 1 order by 2 desc limit 25"))
    print("shipment_evidence_line on OC naming compuspeed/syntech", q(
        "select case when customer_dealer_token ilike '%%compuspeed%%' then 'compuspeed' "
        "when customer_dealer_token ilike '%%syntech%%' then 'syntech' else 'other' end, count(*) "
        "from shipment_evidence_line where resolved_customer_id = 1 group by 1"))
    print("fact_inbound_shipment on OC naming compuspeed/syntech", q(
        "select case when customer_dealer_token ilike '%%compuspeed%%' then 'compuspeed' "
        "when customer_dealer_token ilike '%%syntech%%' then 'syntech' else 'other' end, count(*) "
        "from fact_inbound_shipment where resolved_customer_id = 1 group by 1"))
    print("DSI staging on OC by token", q(
        "select raw_customer_dealer_token, count(*) from import_distributor_si_staging_line where resolved_customer_id = 1 "
        "group by 1 order by 2 desc limit 15"))
    print("sellout facts on OC: source key / raw token columns", q(
        "select column_name from information_schema.columns where table_name = 'fact_sales_sellout' order by ordinal_position"))
    print("lineup lines on OC by token", q(
        "select column_name from information_schema.columns where table_name = 'commercial_lineup_line' and column_name like '%%token%%'"))
