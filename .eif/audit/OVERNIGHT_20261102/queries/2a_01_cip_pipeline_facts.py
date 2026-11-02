"""2a step 1 (READ-ONLY on cip): every fact that counts in the pipeline figure, one row per fact.

Pipeline = the headline rule in apps/api/app/services/supply_overview.py (_headline_sql): facts of the tenant that are
"kept" (live, no covering shipped twin or an open remainder > 0), line_state = 'open_order', pod_date IS NULL, quantity
= the counted (remainder) quantity. The SQL fragments are imported from the application so the rule is the application's.
Output: 2a_cip_pipeline_facts.json (rows) and a summary on stdout.
"""
import json
import pathlib

from ro import TENANT, q, run_ro

from app.services.shipment_live_line import live_line_sql
from app.services.shipment_strict_pair import OPEN_TWIN_REMAINDER_SQL, TWIN_COUNTED_QTY_SQL, TWIN_KEPT_SQL

OUT = pathlib.Path(__file__).with_name("2a_cip_pipeline_facts.json")

SQL = f"""
WITH twin_rem AS MATERIALIZED ({OPEN_TWIN_REMAINDER_SQL})
SELECT fact_inbound_shipment.id AS fact_id,
       fact_inbound_shipment.import_job_id AS job_id,
       fact_inbound_shipment.report_type,
       fact_inbound_shipment.source_sheet,
       fact_inbound_shipment.line_state,
       fact_inbound_shipment.status,
       fact_inbound_shipment.operating_unit,
       fact_inbound_shipment.order_no,
       fact_inbound_shipment.order_line,
       fact_inbound_shipment.delivery_no,
       fact_inbound_shipment.item_code,
       fact_inbound_shipment.customer_po,
       fact_inbound_shipment.purchase_order_id,
       fact_inbound_shipment.product_id,
       fact_inbound_shipment.quantity AS stored_qty,
       {TWIN_COUNTED_QTY_SQL} AS counted_qty,
       (twin_rem.fact_id IS NOT NULL) AS has_twin_row,
       fact_inbound_shipment.ship_confirm_date,
       fact_inbound_shipment.created_at,
       fact_inbound_shipment.source_key,
       fact_inbound_shipment.fact_upsert_key,
       fact_inbound_shipment.shipment_evidence_line_id
FROM fact_inbound_shipment
LEFT JOIN twin_rem ON twin_rem.fact_id = fact_inbound_shipment.id
WHERE fact_inbound_shipment.tenant_id = :tenant
  AND {TWIN_KEPT_SQL}
  AND {live_line_sql()}
  AND fact_inbound_shipment.pod_date IS NULL
  AND fact_inbound_shipment.line_state = 'open_order'
"""


async def work(db):
    rows = await q(db, SQL, tenant=TENANT)
    OUT.write_text(json.dumps(rows, indent=0), encoding="utf-8")
    tot = sum(r["counted_qty"] or 0 for r in rows)
    print("pipeline facts", len(rows), "counted units", tot)
    by = {}
    for r in rows:
        k = (r["job_id"], r["report_type"], r["source_sheet"], r["status"])
        a = by.setdefault(k, [0, 0.0, 0.0])
        a[0] += 1
        a[1] += r["counted_qty"] or 0
        a[2] += r["stored_qty"] or 0
    for k, v in sorted(by.items(), key=lambda kv: -kv[1][1]):
        print(k, v)
    # the 27 Oct job id
    jobs = await q(
        db,
        "select id, file_name, status, created_at from import_job where file_name ilike '%Shipped Unshipped 20261027%' order by id",
    )
    print("27 Oct jobs", jobs)


run_ro(work)
