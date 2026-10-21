"""Counts only. No snapshot text."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        dbname = session.execute(text("SELECT current_database()")).scalar()
        print("db_is_cip", dbname == "cip")
        if dbname != "cip":
            return
        rows = session.execute(
            text(
                """
                SELECT
                  count(*) AS observations,
                  count(*) FILTER (WHERE raw_snapshot IS NOT NULL) AS with_snapshot,
                  count(*) FILTER (WHERE parse_flags ? 'quality') AS with_quality,
                  pg_database_size(current_database()) AS db_bytes
                FROM listing_observation
                """
            )
        ).one()
        print("observations", int(rows.observations))
        print("with_snapshot", int(rows.with_snapshot))
        print("with_quality", int(rows.with_quality))
        print("db_mebibytes", int(rows.db_bytes) // (1024 * 1024))


if __name__ == "__main__":
    main()
