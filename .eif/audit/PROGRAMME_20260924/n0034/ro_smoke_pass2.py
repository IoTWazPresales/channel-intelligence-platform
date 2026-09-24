"""N-0034 pass 2 read-only smoke: GET the pass-2 list endpoints in-process against the configured DB
(reads only; GET handlers that select and serialize) and check every offered registry field is present
in every returned row."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "apps", "api"))
os.environ.setdefault("CIP_AUTH_MODE", "stub")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services.grid_fields import GRID_FIELDS, grid_field_items  # noqa: E402

with SessionLocal() as s:
    print("current_database:", s.execute(text("select current_database()")).scalar())

API = "/api/v1"
DIST = 29  # most shipment-evidence lines on cip (read-only probe)
URLS = {
    "channel-ops.sell-out": (f"{API}/channel-ops/sell-out?page_size=50", "items"),
    "channel-ops.movements": (f"{API}/channel-ops/movements?distributor_id={DIST}&page_size=50", "items"),
    "channel-ops.inventory": (f"{API}/channel-ops/inventory?distributor_id={DIST}", "items"),
    "cover.distribution": (f"{API}/channel-ops/cover-distribution", "items"),
    "pve.drill": (f"{API}/plan-vs-executed", "drill_rows"),
    "channel-intelligence": (f"{API}/channel-intelligence?page_size=50", "items"),
    "listings": (f"{API}/listing-capture/listings?page_size=200", "items"),
    "customer-terms": (f"{API}/commercial-planner/customer-terms", None),
}
c = TestClient(app)
for grid, (url, key) in URLS.items():
    r = c.get(url)
    body = r.json()
    rows = body if key is None else (body.get(key) or [])
    offered = {i["field"] for i in grid_field_items(GRID_FIELDS[grid])}
    missing: set[str] = set()
    for row in rows:
        missing |= offered - set(row)
    print(f"{grid}: HTTP {r.status_code} rows={len(rows)} offered={len(offered)} missing={sorted(missing)}")
    if rows:
        refs = {
            k: sum(1 for row in rows if row.get(k) not in (None, ""))
            for k in ("customer_code", "customer_name", "distributor_code", "distributor_name")
            if k in rows[0]
        }
        if refs:
            print("   reference keys populated (rows with a value):", refs)
for grid in sorted(GRID_FIELDS):
    r = c.get(f"{API}/grid-fields/{grid}")
    print(f"grid-fields/{grid}: HTTP {r.status_code} items={len(r.json().get('items', []))}")
