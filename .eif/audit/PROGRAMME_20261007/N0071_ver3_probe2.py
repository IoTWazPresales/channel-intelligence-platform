"""GOV-008 RUN-20261008-N0071-VER3 probe 2: when did the evidence relation change since VER2 (14:09+02)?

Read-only (default_transaction_read_only=on, SET TRANSACTION READ ONLY, statement_timeout 60s), prints
current_database() first, rolls back. Aggregates only; no secret printed.
"""
from __future__ import annotations

import json
from pathlib import Path

import psycopg

from app.core.config import get_settings

OUT = Path(__file__).with_name("N0071_ver3_probe2_out.json")


def _dsn() -> str:
    url = get_settings().database_url_sync
    for pre in ("postgresql+psycopg2://", "postgresql+psycopg://"):
        if url.startswith(pre):
            return "postgresql://" + url[len(pre):]
    return url


def main() -> None:
    out: dict = {}
    with psycopg.connect(_dsn(), options="-c default_transaction_read_only=on -c statement_timeout=60000") as c:
        cur = c.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SELECT current_database()")
        out["current_database"] = cur.fetchone()[0]
        print("current_database:", out["current_database"], flush=True)
        cur.execute("SHOW transaction_read_only")
        out["transaction_read_only"] = cur.fetchone()[0]
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = "
                    "'shipment_evidence_observation' AND data_type LIKE 'timestamp%' ORDER BY ordinal_position")
        cols = [r[0] for r in cur.fetchall()]
        out["observation_ts_columns"] = cols
        for col in cols:
            cur.execute(f"SELECT max({col}), count(*) FILTER (WHERE {col} >= timestamptz '2026-10-08 14:09+02') "
                        "FROM shipment_evidence_observation")
            mx, n = cur.fetchone()
            out[f"observation_{col}"] = {"max": str(mx), "rows_since_ver2": int(n)}
        cur.execute("SELECT max(created_at), max(updated_at), count(*) FROM fact_inbound_shipment")
        a, b, n = cur.fetchone()
        out["fact_inbound_shipment"] = {"max_created": str(a), "max_updated": str(b), "rows": int(n)}
        cur.execute("SELECT id, status, template_slug, created_at, completed_at FROM import_job "
                    "WHERE created_at >= timestamptz '2026-10-08 00:00+02' ORDER BY id")
        out["import_jobs_today"] = [[str(x) for x in r] for r in cur.fetchall()]
        cur.execute("SHOW transaction_read_only")
        out["transaction_read_only_end"] = cur.fetchone()[0]
        c.rollback()
    txt = json.dumps(out, indent=2)
    OUT.write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
