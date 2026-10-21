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
    "SELECT datname FROM pg_database WHERE datname LIKE 'cip%' ORDER BY 1"
).fetchall()
for (name,) in rows:
    print(name)
conn.close()
