"""N-0034 pass 1 read-only smoke: GET the adopted list endpoints in-process against the configured DB
(reads only) and check every offered registry field is present in every returned row."""

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
URLS = {
    "roadmap": f"{API}/roadmap",
    "buy-plans": f"{API}/buy-plans",
    "pricing.facts": f"{API}/pricing/facts",
    "pricing.recommendations": f"{API}/pricing/recommendations",
    "inventory.customer": f"{API}/inventory/customer",
    "forecasts": f"{API}/forecasts?limit=50",
    "sellout.commercial-lines": f"{API}/sellout/commercial-lines?limit=20",
    "inbound-shipments": f"{API}/shipping/lines?limit=20",
}
c = TestClient(app)
for grid, url in URLS.items():
    r = c.get(url)
    body = r.json()
    rows = body["items"] if isinstance(body, dict) else body
    offered = {i["field"] for i in grid_field_items(GRID_FIELDS[grid])}
    missing: set[str] = set()
    for row in rows:
        missing |= offered - set(row)
    print(f"{grid}: HTTP {r.status_code} rows={len(rows)} offered={len(offered)} missing={sorted(missing)}")
    if rows:
        row = rows[0]
        refs = {k: row.get(k) is not None for k in ("customer_code", "customer_name", "distributor_code", "distributor_name") if k in row}
        if refs:
            print("   reference keys populated on first row:", refs)
for grid in sorted(GRID_FIELDS):
    r = c.get(f"{API}/grid-fields/{grid}")
    print(f"grid-fields/{grid}: HTTP {r.status_code} items={len(r.json().get('items', []))}")
