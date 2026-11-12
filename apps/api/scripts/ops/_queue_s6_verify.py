"""Read-only check after the BACKLOG-139 apply. Prints counts only."""
from __future__ import annotations

import sys
from pathlib import Path

WORKTREE_API = Path(__file__).resolve().parents[2]
MAIN_API = Path(__file__).resolve().parents[6] / "apps" / "api"
sys.path.insert(0, str(MAIN_API))
sys.path.insert(0, str(WORKTREE_API))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

SQL = text(
    """
    SELECT current_database() AS db,
           (SELECT version_num FROM alembic_version) AS alembic,
           (SELECT count(*) FROM cpor_case) AS cases,
           (SELECT count(*) FROM cpor_case_event) AS events,
           (SELECT count(*) FROM cpor_case WHERE status IS DISTINCT FROM workflow_status) AS status_ne,
           (SELECT count(*) FROM cpor_case_event WHERE event_type = 'workflow_status_repair') AS repairs
    """
)
ROWS = text(
    """
    SELECT id, case_code, origin, status, workflow_status
    FROM cpor_case
    WHERE id IN (3, 309, 310, 311)
    ORDER BY id
    """
)


def main() -> int:
    url = sqlalchemy_sync_engine_url(get_settings().database_url_sync)
    engine = create_engine(url)
    with engine.connect() as conn:
        row = conn.execute(SQL).mappings().one()
        print(dict(row))
        for item in conn.execute(ROWS).mappings():
            print(dict(item))
        conn.rollback()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
