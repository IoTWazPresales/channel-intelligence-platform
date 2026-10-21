"""N-0071 read-only: new (uncorrelated) strict-pair predicate on cip: counts, timing, plan. SELECT only."""
from __future__ import annotations

import json
import time

from sqlalchemy import create_engine, func, select, text

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services.shipment_strict_pair import OPEN_HAS_SHIPPED_TWIN_SQL as TWIN
from app.services.shipment_strict_pair import exclude_open_when_shipped_twin

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)

OPEN_TWIN = f"(lower(line_state) = 'open_order' AND {TWIN})"
OLD_TWIN = """
EXISTS (
  SELECT 1
  FROM fact_inbound_shipment shipped_twin
  WHERE shipped_twin.tenant_id = fact_inbound_shipment.tenant_id
    AND shipped_twin.id <> fact_inbound_shipment.id
    AND lower(shipped_twin.line_state) = 'shipped'
    AND trim(coalesce(fact_inbound_shipment.order_no, '')) <> ''
    AND trim(coalesce(fact_inbound_shipment.item_code, '')) <> ''
    AND lower(trim(coalesce(shipped_twin.operating_unit, '')))
        = lower(trim(coalesce(fact_inbound_shipment.operating_unit, '')))
    AND lower(trim(shipped_twin.order_no)) = lower(trim(fact_inbound_shipment.order_no))
    AND lower(trim(shipped_twin.item_code)) = lower(trim(fact_inbound_shipment.item_code))
)
"""


def impact(twin: str) -> str:
    ot = f"(lower(line_state) = 'open_order' AND {twin})"
    return f"""SELECT
      count(*) FILTER (WHERE {ot}) AS pair_open_rows,
      md5(coalesce(string_agg(id::text, ',' ORDER BY id) FILTER (WHERE {ot}), '')) AS pair_open_ids_md5,
      coalesce(sum(quantity) FILTER (WHERE {ot}),0) AS pair_open_qty,
      coalesce(sum(amount) FILTER (WHERE {ot}),0) AS pair_open_amount,
      count(*) FILTER (WHERE status IS DISTINCT FROM 'received' AND {ot}) AS brief_not_received_lines,
      count(*) FILTER (WHERE pod_date IS NULL AND {ot}) AS lineup_pipeline_lines,
      coalesce(sum(quantity) FILTER (WHERE pod_date IS NULL AND {ot}),0) AS lineup_pipeline_qty,
      coalesce(sum(quantity) FILTER (WHERE pod_date IS NULL AND purchase_order_id IS NOT NULL AND {ot}),0) AS lineup_pipeline_qty_with_po,
      count(*) FILTER (WHERE status='scheduled' AND pod_date IS NULL AND {ot}) AS scheduled_no_pod_lines,
      coalesce(sum(quantity) FILTER (WHERE status='scheduled' AND pod_date IS NULL AND {ot}),0) AS scheduled_no_pod_qty,
      count(*) FILTER (WHERE status='scheduled' AND pod_date IS NULL AND shipment_evidence_line_id IS NOT NULL AND {ot}) AS eta_shift_scope_lines,
      count(*) FILTER (WHERE pod_date IS NOT NULL AND {ot}) AS pod_not_null_lines,
      coalesce(sum(quantity) FILTER (WHERE purchase_order_id IS NOT NULL AND unit_price > 0 AND quantity > 0 AND {ot}),0) AS mac_po_price_qty,
      coalesce(sum(quantity) FILTER (WHERE resolved_distributor_id IS NOT NULL AND product_id IS NOT NULL AND {ot}),0) AS attribution_resolved_dist_qty,
      coalesce(sum(quantity) FILTER (WHERE distributor_id IS NOT NULL AND product_id IS NOT NULL AND pod_date IS NULL AND {ot}),0) AS cover_in_transit_qty
    FROM fact_inbound_shipment"""


RAW = {
    "impact_new_predicate": impact(TWIN),
    "status_of_pair_opens": f"SELECT status, count(*) FILTER (WHERE lower(line_state)='open_order' AND {TWIN}), coalesce(sum(quantity) FILTER (WHERE lower(line_state)='open_order' AND {TWIN}),0) FROM fact_inbound_shipment GROUP BY status ORDER BY status",
    "qty_compare": f"""
        WITH o AS MATERIALIZED (
          SELECT f.id, f.tenant_id, f.quantity oq, f.order_line o_line,
                 lower(trim(coalesce(f.operating_unit,''))) ou, lower(trim(f.order_no)) ord, lower(trim(f.item_code)) item
          FROM fact_inbound_shipment f
          WHERE lower(f.line_state)='open_order'
            AND trim(coalesce(f.order_no,'')) <> '' AND trim(coalesce(f.item_code,'')) <> ''
        ), t AS MATERIALIZED (
          SELECT tenant_id, quantity, order_line,
                 lower(trim(coalesce(operating_unit,''))) ou, lower(trim(order_no)) ord, lower(trim(item_code)) item
          FROM fact_inbound_shipment
          WHERE lower(line_state)='shipped' AND order_no IS NOT NULL AND item_code IS NOT NULL
        ), s AS (
          SELECT o.id, sum(t.quantity) sq, count(*) ns,
                 bool_or(coalesce(t.order_line,'') = coalesce(o.o_line,'')) any_same_line
          FROM o JOIN t
            ON t.tenant_id=o.tenant_id AND t.ou=o.ou AND t.ord=o.ord AND t.item=o.item
          GROUP BY o.id
        )
        SELECT count(*) pairs,
               count(*) FILTER (WHERE o.oq = s.sq) open_eq_shipped,
               count(*) FILTER (WHERE o.oq < s.sq) open_lt_shipped,
               count(*) FILTER (WHERE o.oq > s.sq) open_gt_shipped,
               count(*) FILTER (WHERE s.ns > 1) multi_shipped_twins,
               count(*) FILTER (WHERE s.any_same_line) same_order_line,
               count(*) FILTER (WHERE NOT s.any_same_line) different_order_line,
               coalesce(sum(o.oq),0) open_q, coalesce(sum(s.sq),0) shipped_q,
               coalesce(sum(o.oq) FILTER (WHERE o.oq > s.sq),0) open_q_where_gt,
               coalesce(sum(o.oq) FILTER (WHERE NOT s.any_same_line),0) open_q_diff_line
        FROM o JOIN s USING (id)
    """,
    "join_formulation_ids_md5": """
        WITH o AS MATERIALIZED (
          SELECT id, tenant_id, lower(trim(coalesce(operating_unit,''))) ou, lower(trim(order_no)) ord, lower(trim(item_code)) item
          FROM fact_inbound_shipment
          WHERE lower(line_state)='open_order' AND trim(coalesce(order_no,'')) <> '' AND trim(coalesce(item_code,'')) <> ''
        ), t AS MATERIALIZED (
          SELECT DISTINCT tenant_id, lower(trim(coalesce(operating_unit,''))) ou, lower(trim(order_no)) ord, lower(trim(item_code)) item
          FROM fact_inbound_shipment
          WHERE lower(line_state)='shipped' AND order_no IS NOT NULL AND item_code IS NOT NULL
        )
        SELECT count(*), md5(coalesce(string_agg(o.id::text, ',' ORDER BY o.id), ''))
        FROM o JOIN t ON t.tenant_id=o.tenant_id AND t.ou=o.ou AND t.ord=o.ord AND t.item=o.item
    """,
    "open_rows_with_pod_any": "SELECT count(*) FROM fact_inbound_shipment WHERE lower(line_state)='open_order' AND pod_date IS NOT NULL",
}

out: dict[str, object] = {}
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    c.execute(text("SET statement_timeout = '240s'"))
    out["current_database"] = c.execute(text("SELECT current_database()")).scalar()
    print("current_database =", out["current_database"], flush=True)
    for k, sql in RAW.items():
        t = time.time()
        rows = c.execute(text(sql)).all()
        out[k] = {"rows": [[str(v) for v in r] for r in rows], "seconds": round(time.time() - t, 3)}
        print(k, out[k], flush=True)
    # Run 1 (N0071_probe_new_out_run1.txt): the old correlated EXISTS form of impact() hit the
    # 240 s statement_timeout. Not re-run here.
    out["impact_old_correlated_predicate"] = {"error": "statement_timeout", "seconds": 240.013}
    kept = exclude_open_when_shipped_twin(F)
    orm = select(
        func.count().filter(~kept),
        func.coalesce(func.sum(F.quantity).filter(~kept), 0),
        func.count().filter(kept),
        func.coalesce(func.sum(F.quantity).filter(kept), 0),
    ).select_from(F)
    t = time.time()
    r = c.execute(orm).one()
    out["orm_helper_dropped_and_kept"] = {"rows": [str(v) for v in r], "seconds": round(time.time() - t, 3)}
    t = time.time()
    r = c.execute(select(func.count(), func.coalesce(func.sum(F.quantity), 0)).where(kept)).one()
    out["orm_helper_where_form_kept"] = {"rows": [str(v) for v in r], "seconds": round(time.time() - t, 3)}
    plan = c.execute(text("EXPLAIN " + impact(TWIN))).all()
    out["plan_new_predicate_filter_form"] = [p[0] for p in plan]
    c.rollback()
print(json.dumps(out, indent=1, default=str))
