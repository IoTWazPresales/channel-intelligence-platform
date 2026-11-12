"""List login roles that can create a database. No passwords."""

from sqlalchemy import create_engine, text

engine = create_engine(
    "postgresql+psycopg://cip:cip@127.0.0.1:5432/postgres",
    isolation_level="AUTOCOMMIT",
)
with engine.connect() as conn:
    rows = conn.execute(
        text(
            "SELECT rolname, rolsuper, rolcreatedb, rolcanlogin "
            "FROM pg_roles WHERE rolsuper OR rolcreatedb ORDER BY rolname"
        )
    ).all()
for row in rows:
    print(row.rolname, "super", row.rolsuper, "createdb", row.rolcreatedb, "login", row.rolcanlogin)
