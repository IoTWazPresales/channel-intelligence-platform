"""Read-only NUMBER RULE proof for Supply & Inbound headlines on cip.

Prints current_database() first, then the production supply_overview payload.
Does not write. Does not change a number to match lab fixtures.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services.supply_overview import supply_overview


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname}")
        if dbname != "cip":
            print("REFUSE: expected cip")
            return 2
        payload = await supply_overview(db, user=None)
        keys = [
            "open_lines",
            "eta_past_no_pod_lines",
            "oldest_days_past_eta",
            "oldest_eta_past",
            "landed_pod_iso_week",
            "pipeline_units",
            "shipped_lines",
            "landed_lines",
            "po_observed",
            "po_linked",
            "po_coverage_ratio",
            "overdue_commercial_lines",
            "data_unavailable",
            "lifecycle",
        ]
        out = {k: payload.get(k) for k in keys}
        print(json.dumps(out, default=str, indent=2))
        print("number_class", payload.get("number_class"))
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
