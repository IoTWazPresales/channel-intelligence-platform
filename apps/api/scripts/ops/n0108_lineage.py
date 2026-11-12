"""EXPLAIN the inbound lineage query the row-security helper runs. Read-only, cip only."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

import psycopg
from psycopg.rows import dict_row

OUT = Path(__file__).with_name("n0108_lineage_out.txt")

BODY = """
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
WITH ni AS (
  SELECT f.id, f.shipment_evidence_line_id AS line_id
  FROM public.fact_inbound_shipment f WHERE f.product_id IS NULL
), k AS (
  SELECT DISTINCT o.evidence_line_id, o.line_identity_key
  FROM public.shipment_evidence_observation o JOIN ni ON ni.line_id = o.evidence_line_id
), kl AS (
  SELECT k.evidence_line_id, (
    SELECT r.product_id::bigint
    FROM public.shipment_evidence_observation r
    WHERE r.line_identity_key = k.line_identity_key AND r.product_id IS NOT NULL
    ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC
    LIMIT 1
  ) AS pid
  FROM k
)
SELECT ni.id::bigint, COALESCE(max(s.product_id)::bigint, max(kl.pid))
FROM ni
LEFT JOIN public.shipment_evidence_line s ON s.id = ni.line_id
LEFT JOIN kl ON kl.evidence_line_id = ni.line_id
GROUP BY ni.id
"""


def walk(node, lines, depth=0):
    bits = [node.get("Node Type"), f"{node.get('Actual Total Time')}ms", f"rows={node.get('Actual Rows')}"]
    if node.get("Relation Name"):
        bits.append(node["Relation Name"])
    if node.get("Index Name"):
        bits.append(node["Index Name"])
    lines.append(f"{'  ' * depth}{' '.join(bits)}")
    for child in node.get("Plans") or []:
        walk(child, lines, depth + 1)


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
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM fact_inbound_shipment WHERE product_id IS NULL) AS inbound_null_product,
              (SELECT count(*) FROM shipment_evidence_line WHERE product_id IS NULL) AS line_null_product,
              (SELECT reltuples::bigint FROM pg_class WHERE relname = 'shipment_evidence_observation') AS obs_tuples,
              (SELECT pg_size_pretty(pg_total_relation_size('shipment_evidence_observation'))) AS obs_size,
              (SELECT pg_size_pretty(pg_total_relation_size('shipment_evidence_line'))) AS line_size
            """
        ).fetchone()
        lines.append(
            "inbound_null_product={inbound_null_product} line_null_product={line_null_product} "
            "obs_tuples={obs_tuples} obs_size={obs_size} line_size={line_size}".format(**counts)
        )
        plan = conn.execute(BODY).fetchone()
        payload = plan[next(iter(plan))]
        if isinstance(payload, str):
            payload = json.loads(payload)
        lines.append(
            f"execution_ms={payload[0].get('Execution Time')} planning_ms={payload[0].get('Planning Time')}"
        )
        walk(payload[0]["Plan"], lines)
        conn.rollback()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    main()
