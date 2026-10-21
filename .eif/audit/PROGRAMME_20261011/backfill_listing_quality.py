"""Stamp quality onto stored snapshots. No fetch. Prints counts only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.listing_capture.quality import backfill_stored_snapshots  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        dbname = session.execute(text("SELECT current_database()")).scalar()
        print("db_is_cip", dbname == "cip")
        if dbname != "cip":
            return
        result = backfill_stored_snapshots(session, only_missing=True)
        session.commit()
        print("stamped", result["stamped"])
        print("skipped_no_snapshot", result["skipped_no_snapshot"])
        flags = session.execute(
            text(
                """
                SELECT count(*) FROM listing_observation
                WHERE parse_flags ? 'quality'
                """
            )
        ).scalar()
        print("rows_with_quality", int(flags or 0))


if __name__ == "__main__":
    main()
