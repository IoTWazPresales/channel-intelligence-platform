"""READ-ONLY: call the on-the-water handler in-process on cip (read-only session) and print the tile figures.

    apps/api/.venv/Scripts/python.exe -X utf8 .eif/audit/REVIEW_20261102/deploy/otw_figures.py <tag>
Imports the code in the working tree (= the batch-3 head). Same code the restarted API runs. Writes otw_<tag>_inproc.json.
"""
import asyncio
import json
import sys

sys.path.insert(0, "apps/api")

from sqlalchemy import text  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402

tag = sys.argv[1] if len(sys.argv) > 1 else "run"


async def main():
    from app.api.v1.endpoints.shipping_water import on_the_water

    async with AsyncSessionLocal() as db:
        await db.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
        await db.execute(text("SET TRANSACTION READ ONLY"))
        assert (await db.execute(text("select current_database()"))).scalar_one() == "cip"
        req = Request({"type": "http", "method": "GET", "query_string": b"", "headers": [], "path": "/api/v1/shipping/on-the-water"})
        payload = await on_the_water(req, db, {"tenant_id": "default", "id": 0, "role": "admin"})
        await db.rollback()
    open(f".eif/audit/REVIEW_20261102/deploy/otw_{tag}_inproc.json", "w", encoding="utf-8").write(json.dumps(payload, indent=1, sort_keys=True, default=str))
    print("top-level keys:", sorted(payload.keys()))
    for k, v in payload.items():
        if k in ("vessels", "lines", "ports", "lanes", "needs_look_lines"):
            print(k, "count =", len(v) if hasattr(v, "__len__") else v)
        else:
            print(k, "=", json.dumps(v, default=str)[:600])


asyncio.run(main())
