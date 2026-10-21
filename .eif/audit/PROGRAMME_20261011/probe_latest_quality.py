"""Why the latest observation is missing a quality stamp. Counts only."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT
                  count(*) AS listings,
                  count(*) FILTER (WHERE o.id IS NULL) AS no_observation,
                  count(*) FILTER (WHERE o.raw_snapshot IS NULL) AS latest_no_snapshot,
                  count(*) FILTER (
                    WHERE o.raw_snapshot IS NOT NULL AND NOT (coalesce(o.parse_flags, '{}'::jsonb) ? 'quality')
                  ) AS latest_snapshot_unstamped,
                  count(*) FILTER (WHERE coalesce(o.parse_flags, '{}'::jsonb) ? 'quality') AS latest_stamped
                FROM customer_listing l
                LEFT JOIN LATERAL (
                    SELECT id, raw_snapshot, parse_flags
                    FROM listing_observation
                    WHERE listing_id = l.id
                    ORDER BY fetched_at DESC
                    LIMIT 1
                ) o ON true
                """
            )
        ).one()
        print("db_is_cip", session.execute(text("SELECT current_database()")).scalar() == "cip")
        print("listings", int(row.listings))
        print("no_observation", int(row.no_observation))
        print("latest_no_snapshot", int(row.latest_no_snapshot))
        print("latest_snapshot_unstamped", int(row.latest_snapshot_unstamped))
        print("latest_stamped", int(row.latest_stamped))


if __name__ == "__main__":
    main()
