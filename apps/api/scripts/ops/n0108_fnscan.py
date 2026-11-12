"""Name the slow function-scan node on the line-scoped inbound max. Read-only, cip only."""

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

OUT = Path(__file__).with_name("n0108_fnscan_out.txt")

SQL = """
EXPLAIN (ANALYZE, VERBOSE, FORMAT JSON)
SELECT max(coalesce(ship_confirm_date, pod_date))
FROM fact_inbound_shipment
WHERE tenant_id = 'default'
"""


def walk(node, lines, depth=0):
    extra = []
    for key in ("Relation Name", "Function Name", "Schema", "Index Name"):
        if node.get(key):
            extra.append(f"{key}={node[key]}")
    filt = node.get("Filter") or ""
    if filt:
        extra.append("filter=" + filt[:180])
    lines.append(
        f"{'  ' * depth}{node.get('Node Type')} {node.get('Actual Total Time')}ms "
        f"rows={node.get('Actual Rows')} {' '.join(extra)}"
    )
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
        defs = conn.execute(
            """
            SELECT proname, pg_get_functiondef(oid) AS def
            FROM pg_proc
            WHERE proname IN ('cip_product_line_visible', 'cip_product_line_editable')
            """
        ).fetchall()
        for row in defs:
            lines.append(f"FUNC {row['proname']}:\n{row['def']}")
        conn.execute("SELECT set_config('cip.product_lines', 'NB', true)")
        shown = conn.execute("SELECT current_setting('cip.product_lines', true)").fetchone()
        lines.append(f"product_lines={shown['current_setting']!r}")
        plan = conn.execute(SQL).fetchone()
        payload = plan[next(iter(plan))]
        if isinstance(payload, str):
            payload = json.loads(payload)
        walk(payload[0]["Plan"], lines)
        conn.rollback()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    main()
