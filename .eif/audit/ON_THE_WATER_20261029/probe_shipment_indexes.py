"""Read-only: live indexes, constraints and sizes of the three shipment tables on one database.

    python -I .eif/audit/ON_THE_WATER_20261029/probe_shipment_indexes.py <database>
"""
import sys

sys.path.insert(0, "apps/api")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

TABLES = ("fact_inbound_shipment", "shipment_evidence_line", "shipment_evidence_observation")
db = sys.argv[1]
raw = make_url(get_settings().database_url_sync).set(database=db).render_as_string(hide_password=False)
engine = create_engine(sqlalchemy_sync_engine_url(raw))
with engine.connect() as c:
    c.execute(text("SET default_transaction_read_only = on"))
    print("==", db, c.execute(text("select version_num from alembic_version")).scalar())
    for r in c.execute(
        text("select tablename, indexname, indexdef from pg_indexes where tablename = any(:t) order by 1,2"), {"t": list(TABLES)}
    ):
        print(r.tablename, "|", r.indexdef.replace("CREATE ", "").replace(" ON public.", " ON "))
    for r in c.execute(
        text(
            "select conrelid::regclass::text t, conname, pg_get_constraintdef(oid) d from pg_constraint "
            "where conrelid::regclass::text = any(:t) and contype in ('u','c') order by 1,2"
        ),
        {"t": list(TABLES)},
    ):
        print("CON", r.t, r.conname, r.d)
    for r in c.execute(
        text(
            "select relname, reltuples::bigint n, pg_size_pretty(pg_total_relation_size(oid)) sz "
            "from pg_class where relname = any(:t)"
        ),
        {"t": list(TABLES)},
    ):
        print("SIZE", r.relname, r.n, r.sz)
    c.rollback()
