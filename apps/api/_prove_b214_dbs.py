"""Locate the local cluster and list database names. No secrets."""

from sqlalchemy import create_engine, text

engine = create_engine(
    "postgresql+psycopg://cip:cip@127.0.0.1:5432/postgres",
    isolation_level="AUTOCOMMIT",
)
with engine.connect() as conn:
    rows = conn.execute(
        text("SELECT datname, datdba::regrole::text FROM pg_database ORDER BY datname")
    ).all()
for name, owner in rows:
    print("db", name, "owner", owner)
