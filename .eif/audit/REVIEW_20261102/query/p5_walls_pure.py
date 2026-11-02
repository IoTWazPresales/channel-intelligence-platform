"""GOV-008 review 2026-11-02 (N-0115). Pure check (no DB): every v1 refuse_example is kept by a wall
and the v2 planner returns its exact text for the counterpart measure or governed metric.
Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/query/p5_walls_pure.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"

from sqlalchemy import event  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402


@event.listens_for(Engine, "do_connect")
def _no_db(*a, **k):
    raise AssertionError("no database in this probe")


from app.query.model.graph import V2Request, plan_request  # noqa: E402
from app.query.model.loader import default_model  # noqa: E402
from app.semantics.registry import load_catalog  # noqa: E402

LINES = []


def out(s):
    LINES.append(s)
    print(s)


dm = default_model()
cat = load_catalog()
kept = {(k.metric, k.grains, k.text) for w in dm.walls for k in w.keeps}
by_legacy = {m.legacy_key: m.id for m in dm.measures.values() if m.legacy_key}
total = missing = wrong = 0
for metric in cat.metrics:
    for ex in metric.refuse_examples:
        total += 1
        if (metric.key, ex.grains, ex.reason) not in kept:
            missing += 1
            out(f"NOT KEPT: {metric.key} {sorted(ex.grains)}: {ex.reason[:80]}")
        measure = by_legacy.get(metric.key, metric.key)
        plan = plan_request(dm, V2Request(measures=[measure], breakdowns=sorted(ex.grains)), v1_catalog=cat)
        reasons = [r.reason for r in plan.refusals]
        if plan.ok or ex.reason not in reasons:
            wrong += 1
            out(f"V2 TEXT DIFFERS: {measure} {sorted(ex.grains)} ok={plan.ok} got={reasons}")
out(f"v1 refuse_examples={total} not kept by a wall={missing} v2 planner text differs={wrong}")
out(f"walls={len(dm.walls)} models={sorted(dm.models)} base measures={len(dm.measures)} calculated={len(dm.calculated)}")
Path(__file__).with_name("p5_output.txt").write_text("\n".join(LINES) + "\n", encoding="utf-8")
