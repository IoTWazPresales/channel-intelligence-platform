"""Full-database row delete (dev / disaster reset). Same semantics as ``scripts/wipe_database.py``."""

from __future__ import annotations

from app.db.base import Base
from app.db.session_sync import SessionLocal


def wipe_all_application_tables() -> dict[str, int]:
    """Delete all rows from every mapped table in reverse dependency order. Does not drop schema."""
    total_rows = 0
    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            res = session.execute(table.delete())
            total_rows += res.rowcount or 0
        session.commit()
    return {"rows_deleted": total_rows}
