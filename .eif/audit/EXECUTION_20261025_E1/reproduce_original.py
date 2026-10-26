"""Replay the exact reviewed E1 counterexamples against pinned original source.

This is a historical-source reproduction, not final-source verification. Only
portfolio I/O is mocked; the actual original handler and current planner run.
No DB connection is allowed, and no original verification artifact is modified.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api"))
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "do_connect")
def no_database(*args, **kwargs):
    raise AssertionError("No database permitted in historical reproduction")

from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import default_model
from app.query.types import QueryRequest
from app.semantics.registry import load_catalog

PIN = "d069f86c9232a735b87c64bb8f3fe3c7b5916b08"
source = subprocess.check_output(["git", "show", f"{PIN}:apps/api/app/query/handlers/a2_cpor.py"], cwd=ROOT)
original = ModuleType("original_e1_handler")
exec(compile(source, "pinned_original_a2_cpor.py", "exec"), original.__dict__)
original.SessionLocal = MagicMock()
original.build_portfolio_intelligence = MagicMock(return_value={
    "totals": {"support_usd": 100}, "cases_in_scope": 2, "lines_included": 2,
    "by_customer": [{"customer_id": 10, "support_usd": 40}, {"customer_id": 20, "support_usd": 60}],
    "by_bu": [{"bu": "NB", "support_usd": 40}, {"bu": "NR", "support_usd": 60}],
})

async def main():
    out = {"historical_source_commit": PIN, "handler_sha256": hashlib.sha256(source).hexdigest(), "results": []}
    for filters in ({"bu": "NB"}, {"customer": 999}):
        plan = plan_request(default_model(), V2Request(measures=["support_spend"], breakdowns=["customer"], filters=filters), v1_catalog=load_catalog())
        assert plan.ok
        result = await original.handle_a2(None, QueryRequest(metric="support_spend", grains=["customer"], filters=plan.governed_filters), metric_key="support_spend")
        out["results"].append({"filters": filters, "total": result.value, "rows": result.rows})
    assert out["results"][0]["total"] == 100 and len(out["results"][0]["rows"]) == 2
    assert out["results"][1]["total"] == 100 and out["results"][1]["rows"] == []
    print(json.dumps(out, indent=2))

asyncio.run(main())
