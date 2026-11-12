"""Compare the inbound lineage helper with an index-using rewrite. Read-only, cip only."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

import psycopg
from psycopg.rows import dict_row

OUT = Path(__file__).with_name("n0108_lineage_cmp_out.txt")

NEW = """
WITH ni AS MATERIALIZED (
  SELECT f.id, f.shipment_evidence_line_id AS line_id
  FROM public.fact_inbound_shipment f
  WHERE f.product_id IS NULL
)
SELECT ni.id::bigint AS row_id,
       COALESCE(
         (SELECT s.product_id::bigint FROM public.shipment_evidence_line s WHERE s.id = ni.line_id),
         (
           SELECT max(one.pid)
           FROM (
             SELECT DISTINCT ON (o.line_identity_key) (
               SELECT r.product_id::bigint
               FROM public.shipment_evidence_observation r
               WHERE r.line_identity_key = o.line_identity_key
                 AND r.product_id IS NOT NULL
               ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC
               LIMIT 1
             ) AS pid
             FROM public.shipment_evidence_observation o
             WHERE o.evidence_line_id = ni.line_id
             ORDER BY o.line_identity_key
           ) one
         )
       ) AS inherited_product_id
FROM ni
ORDER BY ni.id
"""


def main() -> None:
    lines: list[str] = []
    with psycopg.connect(os.environ["DATABASE_URL_SYNC"], autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '120s'")
        conn.autocommit = False
        conn.execute("SET TRANSACTION READ ONLY")
        db = conn.execute("SELECT current_database()").fetchone()["current_database"]
        lines.append(f"current_database={db}")
        if db != "cip":
            raise SystemExit(f"STOP: database is {db!r}, not cip")
        conn.execute("SELECT set_config('cip.product_lines', '*', true)")
        started = time.perf_counter()
        old = conn.execute(
            "SELECT row_id, inherited_product_id FROM public.cip_inbound_shipment_lineage() ORDER BY row_id"
        ).fetchall()
        old_s = time.perf_counter() - started
        started = time.perf_counter()
        new = conn.execute(NEW).fetchall()
        new_s = time.perf_counter() - started
        old_key = [(r["row_id"], r["inherited_product_id"]) for r in old]
        new_key = [(r["row_id"], r["inherited_product_id"]) for r in new]
        lines.append(f"old_rows={len(old_key)} seconds={old_s:.3f}")
        lines.append(f"new_rows={len(new_key)} seconds={new_s:.3f} equal={old_key == new_key}")
        if old_key != new_key:
            old_map = dict(old_key)
            new_map = dict(new_key)
            missing = [i for i in old_map if i not in new_map][:5]
            extra = [i for i in new_map if i not in old_map][:5]
            differ = [i for i in old_map if i in new_map and old_map[i] != new_map[i]][:5]
            lines.append(f"missing={missing} extra={extra} differ={[(i, old_map[i], new_map[i]) for i in differ]}")
        conn.rollback()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    main()
