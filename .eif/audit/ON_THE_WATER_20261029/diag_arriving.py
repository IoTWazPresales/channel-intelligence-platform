"""READ-ONLY (GET only, in process, stand-in admin) on cip: the 'Arriving this week' tile against vessels due this week by port ETA."""
import asyncio
import json
import sys

sys.path[:0] = ["apps/api", "."]

import httpx  # noqa: E402

from app.core.security import Role, get_current_user, get_optional_current_user  # noqa: E402
from app.main import app  # noqa: E402


async def main() -> None:
    stand_in = {"id": "0", "role": Role.ADMIN, "tenant_id": "default", "email": "check@example.invalid", "display_name": "check"}
    app.dependency_overrides[get_optional_current_user] = lambda: stand_in
    app.dependency_overrides[get_current_user] = lambda: stand_in
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=300) as c:
        s = (await c.get("/api/v1/shipping/commercial-summary")).json()
        for k in ("arriving_this_week", "week_start", "week_end", "as_of", "arriving"):
            if k in s:
                print(k, json.dumps(s[k])[:400])
        print("summary keys:", sorted(s.keys())[:40])
        o = (await c.get("/api/v1/shipping/on-the-water")).json()
        print("as_of", o["as_of"])
        for v in o["vessels"]:
            print("  vessel", v["forwarder"], "ETA", v["eta"], "units", v["units"], "lines", v["lines"], "overdue", v["overdue"])
        # the lines grid for the tile's own cohort, to see which field it counts
        r = await c.get("/api/v1/shipping/lines", params={"cohort": "arriving_week", "limit": 5})
        j = r.json()
        print("cohort arriving_week total:", j.get("total"), "| sample:", [(x.get("eta_date"), x.get("port_eta_date"), x.get("quantity")) for x in j.get("items", [])[:5]])


asyncio.run(main())
