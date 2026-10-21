"""Read-only: who owns cpor_case_line, and is window_start present. No URLs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "api"))

from sqlalchemy import text

from app.db.session_sync import SessionLocal

s = SessionLocal()
try:
    db, user = s.execute(text("SELECT current_database(), current_user")).one()
    print("db=" + str(db))
    print("user=" + str(user))
    if str(db) != "cip":
        raise SystemExit(2)
    owner = s.execute(
        text(
            "SELECT tableowner FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename = 'cpor_case_line'"
        )
    ).scalar()
    print("owner=" + str(owner))
    member = s.execute(
        text("SELECT pg_has_role(current_user, :owner, 'MEMBER')"),
        {"owner": owner},
    ).scalar()
    print("member=" + str(bool(member)))
    col = s.execute(
        text(
            "SELECT EXISTS ("
            " SELECT 1 FROM information_schema.columns"
            " WHERE table_schema = 'public'"
            " AND table_name = 'cpor_case_line'"
            " AND column_name = 'window_start')"
        )
    ).scalar()
    print("window_start=" + str(bool(col)))
    ver = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print("alembic=" + str(ver))
finally:
    s.close()
