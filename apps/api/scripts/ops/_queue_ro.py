"""Read-only: is the queue clone database present, and is a dump running?"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "apps" / "api"))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


DRIFT = """
SELECT id, status, workflow_status
FROM cpor_case
WHERE id IN (3, 309, 310, 311)
ORDER BY id
"""


def inspect(name: str) -> None:
    from urllib.parse import urlparse, urlunparse

    base = get_settings().database_url_sync
    parsed = urlparse(base)
    url = sqlalchemy_sync_engine_url(urlunparse(parsed._replace(path="/" + name)))
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar()
            print("DB", db)
            if db != name:
                print("STOP wrong database")
                return
            try:
                ver = [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))]
            except Exception as exc:  # noqa: BLE001
                ver = ["missing:" + type(exc).__name__]
            print(" alembic", ver)
            try:
                print(" cpor_case", conn.execute(text("SELECT count(*) FROM cpor_case")).scalar())
                for row in conn.execute(text(DRIFT)):
                    print(" case", row[0], row[1], row[2])
            except Exception as exc:  # noqa: BLE001
                print(" cpor_case", type(exc).__name__)
            conn.rollback()
    except Exception as exc:  # noqa: BLE001
        print("DB", name, "unavailable", type(exc).__name__)
    engine.dispose()


def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        names = [
            r[0]
            for r in conn.execute(text("SELECT datname FROM pg_database WHERE datname LIKE 'cip%' ORDER BY 1"))
        ]
        print("databases", ",".join(names))
        conn.rollback()
    engine.dispose()
    for name in ("cip", "cip_n0118_clone", "cip_queue_b139"):
        if name == "cip" or name in names:
            inspect(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
