"""N-0111 repair: READ-ONLY probe part 4 (traceable vs untraceable rows per table). usage: python probe_unmerge4.py <dbname>"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "PROGRAMME_20261014" / "n0110"))

import psycopg  # noqa: E402

from n0110_numbers import url_for  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "cip"
TOK = "(%s ilike '%%%%compuspeed ltd%%%%' or %s ilike '%%%%syntech distribution%%%%')"

with psycopg.connect(url_for(DB)) as conn:
    conn.read_only = True

    def q(sql, *a):
        try:
            return conn.execute(sql, a).fetchall()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            return [("ERR", str(exc)[:300])]

    print("current_database()", q("select current_database()")[0][0], "(read-only)")
    print("shipment_evidence_line on OC with the company names (not the Q/SADC segment names)", q(
        "select customer_dealer_token, count(*) from shipment_evidence_line where resolved_customer_id = 1 and "
        + TOK % ("customer_dealer_token", "customer_dealer_token") + " group by 1"))
    print("fact_inbound_shipment on OC with the company names", q(
        "select customer_dealer_token, count(*) from fact_inbound_shipment where resolved_customer_id = 1 and "
        + TOK % ("customer_dealer_token", "customer_dealer_token") + " group by 1"))
    print("lineup lines on OC by token naming compuspeed/syntech", q(
        "select customer_token, count(*) from commercial_lineup_line where customer_id = 1 and "
        "(customer_token ilike '%%compuspeed%%' or customer_token ilike '%%syntech%%') group by 1"))
    print("lineup lines on OC total", q("select count(*) from commercial_lineup_line where customer_id = 1"))
    print("cpor_case on OC", q("select id, left(coalesce(cast(row_to_json(cpor_case) as text), ''), 200) from cpor_case where customer_id = 1"))
    print("fact_returns on OC columns", q(
        "select column_name from information_schema.columns where table_name = 'fact_returns' order by ordinal_position"))
    print("fact_inventory_reconciliation on OC by distributor", q(
        "select distributor_id, count(*) from fact_inventory_reconciliation where customer_id = 1 group by 1"))
    print("DSI facts on OC: staging token vs fact count (exact link via staging_line_id)", q(
        "select count(*) filter (where s.id is not null and " + TOK % ("s.raw_customer_dealer_token", "s.raw_customer_dealer_token")
        + "), count(*) from fact_sales_sellout f left join import_distributor_si_staging_line s on s.id = f.staging_line_id "
        "where f.customer_id = 1"))
    print("job 96 resolved before or after the absorb", q(
        "select id, status, created_at, updated_at from import_job where id in (43, 96)"))
