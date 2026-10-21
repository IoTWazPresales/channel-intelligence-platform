"""N-0111 repair: READ-ONLY probe. Can the rows of Compuspeed (1152) and Syntech (4145) be traced
inside OPEN_CHANNEL? Also: which customer sell-through files on cip had a plain 'Date' column.

usage: python probe_unmerge.py <dbname>
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "PROGRAMME_20261014" / "n0110"))

import psycopg  # noqa: E402

from n0110_numbers import url_for  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "cip"
IDS = (1152, 4145)

with psycopg.connect(url_for(DB)) as conn:
    conn.read_only = True

    def q(sql, *a):
        try:
            return conn.execute(sql, a).fetchall()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            return f"ERR {exc}"

    print("current_database()", q("select current_database()")[0][0], "(read-only)")
    oc = q("select id, code, name, merged_into_customer_id from dim_customer where upper(code) = 'OPEN_CHANNEL'")
    print("OPEN_CHANNEL", oc)
    oc_id = oc[0][0]
    for r in q("select id, code, name, merged_into_customer_id, status, left(coalesce(notes,''), 600), updated_at "
               "from dim_customer where id in (1152, 4145)"):
        print("record", r)
    print("OPEN_CHANNEL notes merge lines", [
        ln for ln in (q("select coalesce(notes,'') from dim_customer where id = %s", oc_id)[0][0] or "").splitlines()
        if "1152" in ln or "4145" in ln or "merge" in ln.lower()][:20])

    print("platform audit", q(
        "select id, created_at, actor, action, target_type, target_id, left(cast(detail_json as text), 500) "
        "from platform_audit_event where (detail_json::text like '%%1152%%' or detail_json::text like '%%4145%%' "
        "or target_id in ('1152','4145')) order by id"))

    print("aliases on 1152/4145/OC matching names", q(
        "select id, customer_id, distributor_id, raw_token, status, created_from_import_job_id, left(coalesce(notes,''),120) "
        "from customer_source_token_alias where customer_id in (1152, 4145) "
        "or (customer_id = %s and (raw_token ilike '%%compuspeed%%' or raw_token ilike '%%syntech%%')) order by id", oc_id))

    # Every FK column that points at dim_customer.id, and what OPEN_CHANNEL / 1152 / 4145 hold now.
    fks = q("""
        select cl.relname, a.attname
        from pg_constraint c
        join pg_class cl on cl.oid = c.conrelid
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
        where c.contype = 'f' and c.confrelid = 'dim_customer'::regclass
        order by 1, 2""")
    print("FK columns to dim_customer:", len(fks))
    for tbl, col in fks:
        n = q(f'select count(*) filter (where "{col}" = %s), count(*) filter (where "{col}" in (1152, 4145)) from "{tbl}"', oc_id)
        if isinstance(n, str) or n[0][0] or n[0][1]:
            print(f"  {tbl}.{col}: OPEN_CHANNEL={n if isinstance(n, str) else n[0][0]}  1152/4145={'' if isinstance(n, str) else n[0][1]}")

    # Source evidence: raw tokens naming the two companies.
    print("DSI staging by raw customer token", q(
        "select resolved_customer_id, case when raw_customer_dealer_token ilike '%%compuspeed%%' then 'compuspeed' else 'syntech' end, "
        "count(*), count(fact_sellout_row_id), count(fact_inventory_row_id), coalesce(sum(quantity_sold),0) "
        "from import_distributor_si_staging_line where raw_customer_dealer_token ilike '%%compuspeed%%' "
        "or raw_customer_dealer_token ilike '%%syntech%%' group by 1, 2 order by 1, 2"))
    print("DSI staging distinct tokens", q(
        "select raw_customer_dealer_token, resolved_customer_id, count(*) from import_distributor_si_staging_line "
        "where raw_customer_dealer_token ilike '%%compuspeed%%' or raw_customer_dealer_token ilike '%%syntech%%' "
        "group by 1, 2 order by 3 desc limit 20"))
    print("sellout facts on OC linked from those staging lines", q(
        "select f.customer_id, count(*), coalesce(sum(f.units),0) from fact_sales_sellout f "
        "join import_distributor_si_staging_line s on s.fact_sellout_row_id = f.id "
        "where s.raw_customer_dealer_token ilike '%%compuspeed%%' or s.raw_customer_dealer_token ilike '%%syntech%%' group by 1"))
    print("sellout facts on OC total", q("select count(*), coalesce(sum(units),0) from fact_sales_sellout where customer_id = %s", oc_id))
    print("sellout facts on OC with no staging line", q(
        "select count(*) from fact_sales_sellout f where f.customer_id = %s and not exists "
        "(select 1 from import_distributor_si_staging_line s where s.fact_sellout_row_id = f.id)", oc_id))

    shp_cols = q("select column_name from information_schema.columns where table_name = 'fact_inbound_shipment' "
                 "and (column_name like '%%customer%%' or column_name like 'raw%%') order by 1")
    print("fact_inbound_shipment customer/raw columns", shp_cols)
    stg = q("select table_name from information_schema.tables where table_name like 'import_shipment%%staging%%' "
            "or table_name like 'import_%%shipment%%line%%'")
    print("shipment staging tables", stg)

    print("--- CST files with a plain 'Date' column")
    print(q("""
        select s.import_job_id, j.status, count(*), count(s.period_start_date), count(f.id)
        from import_customer_sellthrough_staging_line s
        join import_job j on j.id = s.import_job_id
        left join fact_customer_sellthrough f on f.import_job_id = s.import_job_id and false
        where s.raw_row_payload ? 'Date'
        group by 1, 2 order by 1"""))
