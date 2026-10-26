"""Independent E4 planning probe. No DB, files, services or product mutations."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'apps' / 'api'))
from app.semantics.registry import load_catalog
from app.services.dashboard_definitions import check_definition, definition_for_promotion, runs_v1
from app.query.model.execute import _run_governed

def refuse_connection(*args, **kwargs):
    raise AssertionError('This planning probe must not connect to any database')

async def main():
    cat = load_catalog()
    with patch('sqlalchemy.engine.Engine.connect', refuse_connection), patch('app.semantics.registry.catalog_for_tenant_cached', return_value=cat):
        original = {'query': {'measures': ['dsi_sellout.units'], 'breakdowns': ['bu'], 'filters': {'bu': [None]}}}
        checked = check_definition(original, tenant_id='astra-no-db')
        promoted = definition_for_promotion(original, tenant_id='astra-no-db', execution={'measures': ['dsi_sellout.units'], 'breakdowns': ['bu']})
        print(json.dumps({'case': 'null-own-filter-omitted', 'original': checked.definition, 'promoted': promoted.definition}, default=str))
        original = {'query': {'measures': ['support_spend'], 'breakdowns': ['customer']}}
        checked = check_definition(original, tenant_id='astra-no-db')
        legacy = SimpleNamespace(grains=['customer'], rows=[{'customer_id': n, 'value': 1} for n in range(501)], ok=True, value=501, handler='a2_cpor', status='ok', validation={}, invariants_applied=[], explain={}, data_vintage={}, cache=None)
        async def engine_stub(*args, **kwargs):
            return legacy
        with patch('app.query.engine.execute_query', engine_stub):
            result = await _run_governed(None, checked.plan, tid='astra-no-db', explain_only=False, version='probe')
        print(json.dumps({'case': 'implicit-default-limit', 'definition': checked.definition, 'runs_v1': runs_v1(checked.definition), 'plan_limit': checked.plan.limit, 'v1_rows':len(legacy.rows), 'v2_rows':len(result['rows']), 'v2_truncated':result['truncated']}))

asyncio.run(main())
