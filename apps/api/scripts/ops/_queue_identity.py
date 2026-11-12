"""Read-only identity of Compuspeed, Syntech and OPEN_CHANNEL on cip."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "apps" / "api"))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

CUSTOMERS = """
SELECT id, code, name, customer_status, merged_into_customer_id
FROM dim_customer
WHERE id IN (1152, 4145)
   OR code = 'OPEN_CHANNEL'
   OR name ILIKE '%compuspeed%'
   OR name ILIKE '%syntech%'
ORDER BY id
"""
DISTRIBUTORS = """
SELECT id, code, name
FROM dim_distributor
WHERE name ILIKE '%compuspeed%' OR name ILIKE '%syntech%' OR code ILIKE '%syntech%' OR code ILIKE '%compu%'
ORDER BY id
"""


def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip":
            print("STOP")
            return 2
        print("customers")
        for row in conn.execute(text(CUSTOMERS)):
            print(" ", row[0], row[1], row[2], row[3], row[4])
        print("distributors")
        for row in conn.execute(text(DISTRIBUTORS)):
            print(" ", row[0], row[1], row[2])
        conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
