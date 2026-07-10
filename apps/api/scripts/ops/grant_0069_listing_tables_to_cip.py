"""One-shot: GRANT LC-U1 (0069) listing tables to app role ``cip``.

Run as postgres migrate URL after alembic 0069. Safe to re-run.
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url


def main() -> int:
    s = get_settings()
    if not s.database_url_sync_migrate:
        print("DATABASE_URL_SYNC_MIGRATE required", file=sys.stderr)
        return 2
    eng = create_engine(sqlalchemy_sync_engine_url(s.database_url_sync_migrate))
    with eng.begin() as c:
        db = c.execute(text("SELECT current_database()")).scalar()
        user = c.execute(text("SELECT current_user")).scalar()
        print("db=", db, "user=", user)
        if db != "cip":
            print("REFUSING: not cip", file=sys.stderr)
            return 2
        c.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
                "customer_listing, listing_observation TO cip"
            )
        )
        c.execute(
            text(
                "GRANT USAGE, SELECT ON SEQUENCE "
                "customer_listing_id_seq, listing_observation_id_seq TO cip"
            )
        )
        print("grants_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
