"""READ-ONLY deploy preflight / post-check for migration 20261102_0051 (cip and cip_test). Prints no password.

    apps/api/.venv/Scripts/python.exe -X utf8 .eif/audit/REVIEW_20261102/deploy/preflight_db.py
Every connection sets default_transaction_read_only=on at connect time; a write would raise.
"""
import sys

sys.path.insert(0, "apps/api")

import psycopg  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402

base = make_url(get_settings().database_url_sync)
if base.database != "cip":
    raise SystemExit("STOP: app URL does not point at cip")


def conn(dbname: str):
    u = base.set(drivername="postgresql", database=dbname)
    return psycopg.connect(u.render_as_string(hide_password=False), options="-c default_transaction_read_only=on", connect_timeout=10)


for db in ("cip", "cip_test"):
    with conn(db) as c, c.cursor() as cur:
        cur.execute("select current_database(), current_user, current_setting('default_transaction_read_only'), pg_is_in_recovery(), (select version_num from alembic_version)")
        print(db, cur.fetchone())

with conn("cip") as c, c.cursor() as cur:
    cur.execute("select count(*) from fact_inbound_shipment")
    print("fact_inbound_shipment rows:", cur.fetchone()[0])
    cur.execute(
        "select count(*) from (select tenant_id, fact_upsert_key from fact_inbound_shipment "
        "group by 1,2 having count(*) > 1) d"
    )
    print("(tenant_id, fact_upsert_key) groups with >1 row:", cur.fetchone()[0])
    cur.execute(
        "select conname, pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid = 'fact_inbound_shipment'::regclass and contype = 'u' order by conname"
    )
    for r in cur.fetchall():
        print("unique constraint:", r)
    cur.execute(
        "select indexname, indexdef from pg_indexes where tablename = 'fact_inbound_shipment' "
        "and indexdef ilike '%fact_upsert_key%' order by 1"
    )
    for r in cur.fetchall():
        print("index:", r)
    cur.execute("select pg_get_userbyid(relowner) from pg_class where relname = 'fact_inbound_shipment'")
    print("table owner:", cur.fetchone()[0])
