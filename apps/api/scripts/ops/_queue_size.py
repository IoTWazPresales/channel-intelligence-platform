"""Read-only size of the in-progress step 6 clone."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "apps" / "api"))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        print("current_database()", conn.execute(text("SELECT current_database()")).scalar())
        row = conn.execute(
            text(
                "SELECT datname, pg_size_pretty(pg_database_size(datname)) "
                "FROM pg_database WHERE datname IN ('cip', 'cip_queue_s6', 'cip_queue_b139') ORDER BY 1"
            )
        ).fetchall()
        for item in row:
            print("size", item[0], item[1])
        conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
