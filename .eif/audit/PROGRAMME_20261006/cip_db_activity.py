import os
import psycopg

owner = os.environ.get("PG_OWNER")
if not owner:
    raise SystemExit("PG_OWNER is not set")
conn = psycopg.connect(
    host="127.0.0.1",
    port=5432,
    user="postgres",
    password=owner,
    dbname="postgres",
)
rows = conn.execute(
    """
    SELECT datname, pid, state, left(query, 80)
    FROM pg_stat_activity
    WHERE datname LIKE 'cip%'
    ORDER BY datname, pid
    """
).fetchall()
for row in rows:
    print("\t".join("" if part is None else str(part) for part in row))
conn.close()
