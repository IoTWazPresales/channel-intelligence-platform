"""Independent NUMBER RULE re-exec for N-0011 GOV-008. Prints current_database() first. Read-only."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services.imports.stewardship_summary import stewardship_summary


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname}")
        if dbname != "cip":
            print("REFUSE: expected cip")
            return 2
        out = await stewardship_summary(db, user=None)
        print(json.dumps(out, default=str, indent=2))
        assert out["database"] == "cip"
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
