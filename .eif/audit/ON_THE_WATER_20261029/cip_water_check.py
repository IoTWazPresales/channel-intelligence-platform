"""Read-only: call GET /api/v1/shipping/on-the-water and /lines?vessel=... on the real cip data, in process.

Uses the app with a stand-in admin user for the default tenant (no login, nothing written; both calls are GETs).

    (cd apps/api && DATABASE_URL_SYNC=... python -X utf8 ../../.eif/audit/ON_THE_WATER_20261029/cip_water_check.py)
"""
import asyncio
import json
import sys

sys.path[:0] = ["apps/api", "."]  # run from the project root or from apps/api

import httpx  # noqa: E402

from app.core.security import get_optional_current_user  # noqa: E402
from app.main import app  # noqa: E402


async def main() -> None:
    from app.core.security import Role, get_current_user

    stand_in = {"id": "0", "role": Role.ADMIN, "tenant_id": "default", "email": "check@example.invalid", "display_name": "check"}
    app.dependency_overrides[get_optional_current_user] = lambda: stand_in
    app.dependency_overrides[get_current_user] = lambda: stand_in
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120) as c:
        r = await c.get("/api/v1/shipping/on-the-water")
        print("status", r.status_code)
        d = r.json()
        print("as_of", d["as_of"], "| report", d["report_date"], "age", d["report_age_days"], "stale", d["report_stale"], "| reports", d["reports"])
        for k, v in d["tiles"].items():
            print("tile", k, json.dumps(v)[:300])
        print("vessels", len(d["vessels"]))
        for v in d["vessels"][:12]:
            print(" ", v["forwarder"], "|", v["lane_label"], "| ETA", v["eta"], "slip", v["slip_days"], "overdue", v["overdue"], "| units", v["units"], "lines", v["lines"], "| assumed", v["route_assumed"], "| at", v["x"], v["y"])
        nl = d["needs_look"]
        print("needs_look", None if nl is None else {k: nl[k] for k in ("lines", "units", "since", "on_board_moved")})
        print("ports", [(p["code"], p["waiting_units"], bool(p["condition"])) for p in d["port_rows"]])
        if d["vessels"]:
            key = d["vessels"][0]["key"]
            g = await c.get("/api/v1/shipping/lines", params={"vessel": key, "limit": 500})
            print("vessel filter ->", g.status_code, "rows", len(g.json().get("items", [])), "of expected", d["vessels"][0]["lines"])
        n = await c.get("/api/v1/shipping/lines", params={"cohort": "needs_look", "limit": 500})
        print("needs_look filter ->", n.status_code, "rows", len(n.json().get("items", [])))
        b = await c.get("/api/v1/brief/signals")
        sig = [s for s in b.json()["signals"] if s["id"] == "shipment_needs_look"]
        print("attention row", sig[0]["title"] if sig else None)


asyncio.run(main())
