"""Status counts only. No snapshot text."""
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
        print("db_is_cip", session.execute(text("SELECT current_database()")).scalar() == "cip")
        rows = session.execute(
            text(
                """
                SELECT lower(l.marketplace) AS marketplace,
                       coalesce(o.parse_flags->'quality'->'checks'->'images'->>'status', 'none') AS images,
                       coalesce(o.parse_flags->'quality'->'checks'->'title'->>'status', 'none') AS title,
                       count(*) AS n
                FROM customer_listing l
                LEFT JOIN LATERAL (
                    SELECT parse_flags
                    FROM listing_observation
                    WHERE listing_id = l.id AND raw_snapshot IS NOT NULL
                    ORDER BY fetched_at DESC
                    LIMIT 1
                ) o ON true
                GROUP BY 1, 2, 3
                ORDER BY 1, 4 DESC
                """
            )
        ).all()
        for market, images, title, count in rows:
            print(f"latest_snapshot {market} images {images} title {title} {int(count)}")
        latest = session.execute(
            text(
                """
                SELECT count(*) AS listings,
                       count(*) FILTER (WHERE o.parse_flags ? 'quality') AS latest_with_quality
                FROM customer_listing l
                LEFT JOIN LATERAL (
                    SELECT parse_flags
                    FROM listing_observation
                    WHERE listing_id = l.id
                    ORDER BY fetched_at DESC
                    LIMIT 1
                ) o ON true
                """
            )
        ).one()
        print("listings", int(latest.listings))
        print("latest_with_quality", int(latest.latest_with_quality))


if __name__ == "__main__":
    main()
