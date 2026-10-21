"""N-0111 repair 2: READ-ONLY count of OPEN_CHANNEL (customer id 1) shipment and lineup rows whose
raw source row / raw customer text names Compuspeed or Syntech. usage: python probe_unmerge_raw.py <dbname>"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "PROGRAMME_20261014" / "n0110"))

import psycopg  # noqa: E402

from n0110_numbers import url_for  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "cip"
OC = 1

RAW = "raw_source_row::text"
RAW_TOK = "raw_source_row::text || ' ' || coalesce(customer_dealer_token, '')"
LINEUP_RAW = "coalesce(raw_row_payload::text, '') || ' ' || coalesce(customer_token, '')"
LINEUP_TOK = "coalesce(customer_token, '')"


def hit(expr: str) -> str:
    return (
        f"count(*) filter (where {expr} ilike '%compuspeed%'), "
        f"count(*) filter (where {expr} ilike '%syntech%'), "
        f"count(*) filter (where {expr} ilike '%compuspeed%' or {expr} ilike '%syntech%'), count(*)"
    )


with psycopg.connect(url_for(DB)) as conn:
    conn.read_only = True
    print("current_database()", conn.execute("select current_database()").fetchone()[0], "(read-only)")

    def run(label: str, sql: str) -> None:
        try:
            print(f"{label}: (compuspeed, syntech, either, rows_on_OPEN_CHANNEL) =", conn.execute(sql).fetchone())
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            print(f"{label}: ERR", str(exc)[:300])

    run("fact_inbound_shipment raw only",
        f"select {hit(RAW)} from fact_inbound_shipment where customer_id = {OC} or resolved_customer_id = {OC}")
    run("fact_inbound_shipment raw + token",
        f"select {hit(RAW_TOK)} from fact_inbound_shipment where customer_id = {OC} or resolved_customer_id = {OC}")
    run("shipment_evidence_line raw + token",
        f"select {hit(RAW_TOK)} from shipment_evidence_line where resolved_customer_id = {OC}")
    run("shipment_evidence_observation raw",
        f"select {hit(RAW)} from shipment_evidence_observation where customer_id = {OC}")
    run("shipment_evidence_current raw",
        f"select {hit(RAW)} from shipment_evidence_current where resolved_customer_id = {OC}")
    run("commercial_lineup_line raw payload + token",
        f"select {hit(LINEUP_RAW)} from commercial_lineup_line where customer_id = {OC}")
    run("commercial_lineup_line token only",
        f"select {hit(LINEUP_TOK)} from commercial_lineup_line where customer_id = {OC}")
