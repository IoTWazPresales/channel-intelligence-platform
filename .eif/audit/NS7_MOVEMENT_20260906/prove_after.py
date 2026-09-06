"""Call movement-lens on cip after the ISO-Monday fix. Read-only. Prints current_database() first."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text

from app.api.v1.endpoints.channel_ops import channel_ops_movement_lens
from app.db.session import AsyncSessionLocal


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname}")
        if dbname != "cip":
            print("REFUSE: expected cip")
            return 2
        out = await channel_ops_movement_lens(db=db, user=None, weeks=13)
        h = out.get("headlines") or {}
        series = out.get("sell_out_weekly") or []
        print("headlines", json.dumps(h, default=str))
        print("last_week", series[-1] if series else None)
        print("prior_week", series[-2] if len(series) >= 2 else None)
        print("family_n", len(out.get("family_week") or []))
        growing = [f for f in (out.get("family_week") or []) if (f.get("units") or 0) > 0 and f.get("wow") is not None and f["wow"] > 0]
        print("growing_names", [f["family"] for f in growing])
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
