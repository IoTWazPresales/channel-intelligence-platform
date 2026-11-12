"""Read-only check that migration 20261103_0056's schema effects are on cip.

Prints nullability, the observation index, and whether the current view
still names the line pod_date. Does not write.
"""
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

NULLS = text(
    """
    SELECT column_name, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'shipment_evidence_line'
      AND column_name IN ('report_type', 'line_state', 'raw_source_row')
    ORDER BY column_name
    """
)
INDEX = text(
    """
    SELECT indexdef
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'ix_shipment_ev_obs_evidence_line'
    """
)
VIEW = text("SELECT pg_get_viewdef('public.shipment_evidence_current'::regclass, true)")


def main() -> int:
    url = sqlalchemy_sync_engine_url(get_settings().database_url_sync)
    engine = create_engine(url)
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        alembic = [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))]
        print("current_database()", db)
        print("alembic", alembic)
        if db != "cip":
            print("STOP")
            return 2
        for row in conn.execute(NULLS).mappings():
            print("column", dict(row))
        indexes = [r[0] for r in conn.execute(INDEX)]
        print("index_count", len(indexes))
        for item in indexes:
            print("indexdef", item)
        view = conn.execute(VIEW).scalar() or ""
        print("view_mentions_sel_pod_date", "sel.pod_date" in view)
        print("view_mentions_pod_date", "pod_date" in view)
        conn.rollback()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
