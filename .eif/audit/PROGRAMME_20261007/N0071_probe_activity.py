"""N-0071 read-only: show active queries touching the strict-pair predicate (no secrets)."""
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database =", c.execute(text("SELECT current_database()")).scalar())
    for r in c.execute(text(
        "SELECT pid, state, application_name, now()-query_start AS running, "
        "left(regexp_replace(query, '\\s+', ' ', 'g'), 160) AS q "
        "FROM pg_stat_activity WHERE datname = current_database() AND state <> 'idle' "
        "AND pid <> pg_backend_pid() ORDER BY query_start")).all():
        print(r)
    c.rollback()
