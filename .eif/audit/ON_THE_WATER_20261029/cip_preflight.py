"""Read-only preflight for the cip apply: target database, resolved URLs (password masked), jobs in flight, alembic head.

    python -X utf8 -I .eif/audit/ON_THE_WATER_20261029/cip_preflight.py
"""
import os
import sys

sys.path.insert(0, "apps/api")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

s = get_settings()


def masked(url: str) -> str:
    return make_url(url).render_as_string(hide_password=True)


print("app role sync URL      :", masked(s.database_url_sync))
print("app role async URL     :", masked(s.database_url))
owner = make_url(s.database_url_sync).set(username="postgres", password=os.environ["PG_OWNER"])
print("owner (migration) URL  :", masked(owner.render_as_string(hide_password=False)))
if make_url(s.database_url_sync).database != "cip":
    raise SystemExit("STOP: the app URL does not point at cip")

engine = create_engine(sqlalchemy_sync_engine_url(s.database_url_sync))
with engine.connect() as c:
    c.execute(text("SET default_transaction_read_only = on"))
    print("current_database()     :", c.execute(text("select current_database()")).scalar(), "| role", c.execute(text("select current_user")).scalar())
    print("alembic_version        :", c.execute(text("select version_num from alembic_version")).scalar())
    rows = c.execute(
        text(
            "select status, stage, count(*) from import_job where archived_at is null "
            "and status not in ('completed','failed','cancelled','interrupted','loaded','validation_failed','completed_with_errors') "
            "group by 1,2 order by 3 desc"
        )
    ).all()
    print("import jobs not in a final status (archived excluded):")
    for r in rows:
        print("   ", tuple(r))
    live = c.execute(
        text(
            "select id, status, stage, started_at, completed_at, file_name from import_job "
            "where (started_at is not null and completed_at is null and status in ('running','processing','applying','validating')) "
            "or status in ('running','processing','applying','validating','queued') order by id"
        )
    ).all()
    print("jobs running or queued   :", len(live))
    for r in live:
        print("   ", tuple(r))
    act = c.execute(
        text("select count(*) from pg_stat_activity where datname = 'cip' and state <> 'idle' and pid <> pg_backend_pid()")
    ).scalar()
    print("other active sessions on cip:", act)
    c.rollback()
