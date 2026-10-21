"""N-0071 round 4: read-only look at the probe's own session progress (no secrets printed)."""
from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
    if url.startswith(pre):
        url = "postgresql+psycopg://" + url[len(pre):]
        break
eng = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database:", c.execute(text("SELECT current_database()")).scalar())
    print("cases:", c.execute(text("SELECT count(*) FROM commercial_lineup_case")).scalar())
    print("cases_with_products:", c.execute(text(
        "SELECT count(DISTINCT case_id) FROM commercial_lineup_line WHERE product_id IS NOT NULL")).scalar())
    for r in c.execute(text(
        "SELECT pid, state, wait_event_type, now()-xact_start AS xact_age, now()-query_start AS q_age, left(query, 120) "
        "FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() "
        "AND state <> 'idle' ORDER BY xact_start")).all():
        print(tuple(str(x) for x in r))
    c.rollback()
