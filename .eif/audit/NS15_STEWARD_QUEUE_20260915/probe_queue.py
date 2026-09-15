"""Reproduce steward_failure_queue against cip (read-only)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services.imports.steward_queue import steward_failure_queue  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("SELECT current_database()"))).scalar()
        print(f"current_database()={dbname!r}")
        try:
            out = await steward_failure_queue(db, {"tenant_id": "default"}, limit=5)
            print("total", out["total_candidates"], "groups", len(out["groups"]), "items", len(out["items"]))
            print("group_types", [g["entity_type"] for g in out["groups"]])
            return 0
        except Exception:
            import traceback

            traceback.print_exc()
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
