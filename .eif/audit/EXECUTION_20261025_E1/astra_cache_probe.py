"""Pure E1 cache/refusal probe. SQLAlchemy connections explicitly vetoed."""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api"))
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "do_connect")
def no_database(*args, **kwargs):
    raise AssertionError("Database access forbidden for this pure probe")

from app.query import cache, engine
from app.semantics.registry import load_catalog

engine.catalog_for_tenant_cached = lambda tenant: load_catalog()
cache._redis_checked = True
cache._redis_client = None

async def main():
    cat = load_catalog()
    key = cache.cache_key(tenant_id="fictional-e1", metric="support_spend", grains=["customer"], filters={}, catalog_version=cat.version)
    cache.set_cached(key, {"ok": True, "status": "ok", "metric_key": "support_spend", "grains": ["customer"], "filters": {}, "value": 100.0, "rows": []})
    out = []
    for filters in ({"bu": ""}, {"bu": None}, {"unexpected": None}, {"product_line": ""}, {"customer_id": ""}):
        warm = await engine.execute_query(None, metric="support_spend", grains=["customer"], filters=filters, tenant_id="fictional-e1")
        cold = await engine.execute_query(None, metric="support_spend", grains=["customer"], filters=filters, tenant_id="fictional-e1", skip_cache=True)
        out.append({"filters": filters, "warm": {"ok": warm.ok, "value": warm.value, "cache_hit": warm.cache.hit}, "cold": {"ok": cold.ok, "status": cold.status, "message": cold.message}})
    print(json.dumps(out, indent=2))

asyncio.run(main())
