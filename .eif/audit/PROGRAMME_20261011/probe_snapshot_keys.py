"""Print snapshot key paths only. No page text, no prices."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.listing_capture.observation import decompress_snapshot  # noqa: E402


def paths(obj, prefix="", depth=0):
    if depth > 3:
        return
    if isinstance(obj, dict):
        for key in list(obj.keys())[:40]:
            print(f"{prefix}{key}")
            paths(obj[key], prefix + "  ", depth + 1)
    elif isinstance(obj, list) and obj:
        print(f"{prefix}[list {len(obj)}]")
        paths(obj[0], prefix + "  ", depth + 1)


def main() -> None:
    sql = text(
        """
        SELECT l.marketplace, o.id
        FROM listing_observation o
        JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.raw_snapshot IS NOT NULL
          AND o.parse_status = 'ok'
          AND l.marketplace = :market
        ORDER BY o.fetched_at DESC
        LIMIT 1
        """
    )
    with SessionLocal() as session:
        dbname = session.execute(text("SELECT current_database()")).scalar()
        print("db_is_cip", dbname == "cip")
        if dbname != "cip":
            return
        for market in ("takealot", "evetech", "amazon"):
            row = session.execute(sql, {"market": market}).first()
            print("market", market, "found", row is not None)
            if row is None:
                continue
            blob = session.execute(
                text("SELECT raw_snapshot FROM listing_observation WHERE id = :id"),
                {"id": row.id},
            ).scalar()
            raw = decompress_snapshot(blob)
            print("kind", "json" if raw.lstrip().startswith("{") else "text", "chars", len(raw))
            if raw.lstrip().startswith("{"):
                import json
                data = json.loads(raw)
                paths(data)
            else:
                print("has_jsonld", "application/ld+json" in raw)


if __name__ == "__main__":
    main()
