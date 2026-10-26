"""Pure N-0116 review probes: no database connections, filesystem exports or services.

From repository root:
  apps/api/.venv/Scripts/python.exe -B .eif/audit/PROGRAMME_20261025/n0116_readonly_probes.py
The connection guard makes an accidental SQLAlchemy DB connection fail before opening it.
"""
from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "do_connect")
def refuse_database(*args, **kwargs):
    raise AssertionError("Read-only review probe must never open a database connection")


from app.query.model.loader import default_model
from app.query.model.graph import plan_request
from app.semantics.registry import load_catalog
from app.services.dashboard_definitions import check_definition, runs_v1, request_from_definition
from app.services.report_export import build_xlsx_bytes
from openpyxl import load_workbook


model, catalog = default_model(), load_catalog()
checked = check_definition(
    {"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["product"],
               "sort": {"by": "dsi_sellout.units", "dir": "asc"}, "limit": 1}},
    tenant_id="default", dm=model, v1_catalog=catalog,
)
print(json.dumps({
    "probe": "sort_limit_equivalence", "v1_equivalent": checked.v1_equivalent,
    "runs_v1": runs_v1(checked.definition), "stored_query": checked.definition["query"],
    "v1_mirror": checked.v1.__dict__,
}))

data = build_xlsx_bytes(
    title="Fictional audit", metric_key="dsi_sellout.units", grains=["product"], value=1,
    rows=[{"product_name": "=1+1", "dsi_sellout.units": 1}], data_vintage={},
)
workbook = load_workbook(BytesIO(data), data_only=False)
print(json.dumps({
    "probe": "spreadsheet_literal", "cell_data_type": workbook["Data"]["A2"].data_type,
    "formula_stored": workbook["Data"]["A2"].value,
}))

checked = check_definition(
    {"query": {"measures": ["cst_sellthrough.units_per_week"]}},
    tenant_id="default", dm=model, v1_catalog=catalog,
)
request = request_from_definition(checked.definition)
plan = plan_request(model, request, v1_catalog=catalog)
print(json.dumps({
    "probe": "promotion_requires_dates", "needs_date_range": checked.needs_date_range,
    "saved_from": request.period_from, "saved_to": request.period_to,
    "delivery_plan_ok": plan.ok, "refusals": [item.as_dict() for item in plan.refusals],
}))
