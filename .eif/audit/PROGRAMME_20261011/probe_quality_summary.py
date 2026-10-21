"""Quality stamp counts. No evidence text."""
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

CHECKS = (
    "price_and_stock",
    "title",
    "images",
    "description",
    "key_specs",
    "buy_box",
    "reviews",
)


def main() -> None:
    with SessionLocal() as session:
        print("db_is_cip", session.execute(text("SELECT current_database()")).scalar() == "cip")
        rows = session.execute(
            text(
                """
                SELECT lower(l.marketplace) AS marketplace,
                       o.parse_flags->'quality' AS quality
                FROM customer_listing l
                JOIN LATERAL (
                    SELECT parse_flags
                    FROM listing_observation
                    WHERE listing_id = l.id
                    ORDER BY fetched_at DESC
                    LIMIT 1
                ) o ON true
                WHERE o.parse_flags ? 'quality'
                """
            )
        ).mappings().all()
    by_market: dict[str, int] = {}
    cells: dict[tuple[str, str, str], int] = {}
    for row in rows:
        market = str(row["marketplace"] or "")
        by_market[market] = by_market.get(market, 0) + 1
        quality = row["quality"] if isinstance(row["quality"], dict) else {}
        checks = quality.get("checks") if isinstance(quality.get("checks"), dict) else {}
        for key in CHECKS:
            cell = checks.get(key) if isinstance(checks.get(key), dict) else {}
            status = str(cell.get("status") or "missing")
            bucket = (market, key, status)
            cells[bucket] = cells.get(bucket, 0) + 1
    for market, count in sorted(by_market.items()):
        print(f"listings {market} {count}")
    for (market, key, status), count in sorted(cells.items()):
        print(f"cell {market} {key} {status} {count}")


if __name__ == "__main__":
    main()
