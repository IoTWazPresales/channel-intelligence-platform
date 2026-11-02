#!/usr/bin/env python3
"""Read-only: the inbound-shipment figures the app shows, on whatever database DATABASE_URL points at. Prints JSON.

Calls the real endpoints in process (GET only) as a stand-in admin: supply overview (open, pipeline, shipped, landed),
planning overview (fill rate) and On the water (at sea, vessels, overdue), plus plain SQL totals by line state.
Used by prove_po_less_retire_clone.py before and after the retire; never writes.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import Role, get_current_user, get_optional_current_user  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


def find(obj, name):
    """First value stored under ``name`` anywhere in a nested dict/list."""
    if isinstance(obj, dict):
        if name in obj:
            return obj[name]
        for v in obj.values():
            r = find(v, name)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, name)
            if r is not None:
                return r
    return None


async def main() -> None:
    stand_in = {"id": "0", "role": Role.ADMIN, "tenant_id": "default", "email": "measure@example.invalid", "display_name": "measure"}
    app.dependency_overrides[get_optional_current_user] = lambda: stand_in
    app.dependency_overrides[get_current_user] = lambda: stand_in
    out: dict = {}
    async with engine.connect() as conn:
        await conn.execute(text("SET TRANSACTION READ ONLY"))
        out["database"] = (await conn.execute(text("select current_database()"))).scalar()
        rows = (await conn.execute(text(
            "select line_state, count(*), coalesce(round(sum(quantity)), 0) from fact_inbound_shipment where tenant_id='default' group by 1 order by 1"
        ))).all()
        out["facts_by_line_state"] = {r[0]: {"lines": int(r[1]), "units": float(r[2])} for r in rows}
        await conn.rollback()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=300) as c:
        sup = (await c.get("/api/v1/supply/overview")).json()
        out["supply"] = {k: sup.get(k) for k in ("open_lines", "open_units", "pipeline_lines", "pipeline_units", "shipped_lines", "shipped_units",
                                                  "landed_lines", "landed_units", "arrived_lines", "arrived_units", "eta_past_no_pod_lines")}
        plan = (await c.get("/api/v1/planning/overview")).json()
        out["fill_rate"] = find(plan, "fill_rate")
        out["fill_rate_pct"] = find(plan, "fill_rate_pct")
        otw = (await c.get("/api/v1/shipping/on-the-water")).json()
        vessels = otw.get("vessels", [])
        out["on_the_water"] = {
            "at_sea_units": otw["tiles"]["at_sea"]["units"], "at_sea_lines": otw["tiles"]["at_sea"]["lines"], "vessels": len(vessels),
            "overdue_vessels": sum(1 for v in vessels if v.get("overdue")), "overdue_units": sum(v["units"] for v in vessels if v.get("overdue")),
            "arrived_units": otw["tiles"]["arrived"]["units"], "eta_moved": otw["tiles"]["eta_moved"].get("vessels_moved"),
        }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
