"""Read-only look at cip_test sessions. Stops unless cip_test."""

from __future__ import annotations

import psycopg

with psycopg.connect("postgresql://cip:cip@localhost:5432/cip_test", autocommit=True) as conn:
    conn.execute("SET default_transaction_read_only = on")
    name = conn.execute("SELECT current_database()").fetchone()[0]
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        raise SystemExit(f"STOP: database is {name!r}")
    rows = conn.execute(
        """
        select pid, state, wait_event_type, wait_event, left(query, 180)
        from pg_stat_activity
        where datname = 'cip_test'
        order by pid
        """
    ).fetchall()
    for row in rows:
        print(row, flush=True)
