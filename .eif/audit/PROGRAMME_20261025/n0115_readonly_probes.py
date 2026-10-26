"""Independent final-source probes; fictional values and no database connection.

Mocks only the portfolio I/O for the filter probe. Does not test PostgreSQL RLS.
"""
from pathlib import Path
import asyncio
from dataclasses import replace
import json
import sys
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'apps/api'))
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, 'do_connect')
def refuse_database(*args, **kwargs):
    raise AssertionError('Audit probe must not connect to a database')


from app.query.model.loader import default_model, AGGS, CALC_KINDS
from app.query.model.graph import V2Request, plan_request, measure_breakdowns
from app.query.model.catalog import catalog_v2
from app.query.handlers import a2_cpor
from app.query.types import QueryRequest
from app.semantics.registry import load_catalog, validate_metric_grain


async def main():
    dm, cat = default_model(), load_catalog()
    results = [{'probe': 'capability_inventory', 'models': list(dm.models),
                'aggregates': sorted(AGGS), 'calculations': sorted(CALC_KINDS),
                'period_grains': list(dm.period.grains),
                'walls': len(dm.walls), 'base_measures': len(dm.measures),
                'calculated_measures': len(dm.calculated)}]
    # Verify the original explicit refusal examples remain present verbatim.
    kept = {(k.metric,k.grains,k.text) for wall in dm.walls for k in wall.keeps}
    examples = [(m.key,e.grains,e.reason) for m in cat.metrics for e in m.refuse_examples]
    assert all(e in kept for e in examples)
    assert 'site_label' not in measure_breakdowns(dm, dm.measures['dsi_sellout.units'])
    assert 'site_label' in measure_breakdowns(dm, dm.measures['cst_sellthrough.units'])
    results.append({'probe':'wall_preservation', 'examples_checked':len(examples),
                    'all_kept_verbatim':True,'dsi_cst_site_wall':True})
    payload = {'totals': {'support_usd':100},
               'by_customer':[{'customer_id':10,'support_usd':40},{'customer_id':20,'support_usd':60}],
               'by_bu':[{'bu':'NB','support_usd':40},{'bu':'NR','support_usd':60}],
               'cases_in_scope':2,'lines_included':2}
    for filters in [{'bu':'NB'}, {'customer':999}]:
        req = V2Request(measures=['support_spend'],breakdowns=['customer'],filters=filters)
        plan = plan_request(dm,req,v1_catalog=cat)
        assert plan.ok
        with patch.object(a2_cpor,'SessionLocal',return_value=MagicMock()), patch.object(a2_cpor,'build_portfolio_intelligence',return_value=payload):
            answer = await a2_cpor.handle_a2(None,QueryRequest(metric='support_spend',grains=['customer'],filters=plan.governed_filters,tenant_id='fictional-review'),metric_key='support_spend')
        results.append({'probe':'governed_filter','filters':filters,'planner_ok':plan.ok,
                        'observed_total':answer.value,'observed_rows':answer.rows,
                        'expected':'apply filter to rows and totals or refuse honestly'})
    original = cat.metric_by_key('sellout_units')
    narrowed = replace(original,hidden=True,label='Fictional restricted metric',allowed_grains=(frozenset({'product'}),))
    tenant_catalog=replace(cat,metrics=tuple(narrowed if m.key==original.key else m for m in cat.metrics),tenant_id='fictional-review',overlay_applied=True)
    old=validate_metric_grain('sellout_units',['customer'],catalog=tenant_catalog)
    new=plan_request(dm,V2Request(measures=['dsi_sellout.units'],breakdowns=['customer']),v1_catalog=tenant_catalog)
    entry=next(m for m in catalog_v2(dm,tenant_catalog,is_admin=False)['measures'] if m['id']=='dsi_sellout.units')
    results.append({'probe':'tenant_semantic_restriction','v1_ok':old.ok,'v1_reason':old.message,
                    'v2_ok':new.ok,'non_admin_catalog_label':entry['label'],
                    'non_admin_catalog_breakdowns':entry['breakdowns']})
    path=Path(__file__).with_suffix('.json')
    path.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    asyncio.run(main())
