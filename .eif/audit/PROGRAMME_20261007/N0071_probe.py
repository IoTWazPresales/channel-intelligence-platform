"""N-0071 read-only probe: strict open->shipped pairs in cip. SELECT only, read-only txn."""
from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.services.shipment_strict_pair import OPEN_HAS_SHIPPED_TWIN_SQL as TWIN

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)

OPEN_TWIN = f"(lower(line_state) = 'open_order' AND {TWIN})"

Q = {
    "line_state_counts": "SELECT lower(line_state) ls, status, count(*) n, coalesce(sum(quantity),0) q FROM fact_inbound_shipment GROUP BY 1,2 ORDER BY 1,2",
    "strict_pair_open_rows": f"""
        SELECT count(*) n, coalesce(sum(quantity),0) q, coalesce(sum(amount),0) amt,
               count(*) FILTER (WHERE pod_date IS NOT NULL) with_pod,
               count(*) FILTER (WHERE status = 'received') st_received,
               count(*) FILTER (WHERE status = 'scheduled') st_scheduled,
               count(*) FILTER (WHERE status IS DISTINCT FROM 'received') st_not_received,
               count(*) FILTER (WHERE purchase_order_id IS NOT NULL) with_po,
               count(*) FILTER (WHERE distributor_id IS NOT NULL AND product_id IS NOT NULL) with_dist_prod,
               count(*) FILTER (WHERE customer_id IS NOT NULL) with_customer,
               count(*) FILTER (WHERE ship_confirm_date IS NOT NULL) with_ship_confirm,
               count(*) FILTER (WHERE eta_date IS NOT NULL OR promise_date IS NOT NULL) with_eta_or_promise,
               count(DISTINCT tenant_id) tenants
        FROM fact_inbound_shipment WHERE {OPEN_TWIN}
    """,
    # Quantity comparison open vs the sum of its strict shipped twins
    "qty_compare": f"""
        WITH o AS (
          SELECT f.id, f.tenant_id, f.quantity oq, f.order_line o_line,
                 lower(trim(coalesce(f.operating_unit,''))) ou, lower(trim(f.order_no)) ord, lower(trim(f.item_code)) item
          FROM fact_inbound_shipment f
          WHERE lower(f.line_state)='open_order' AND {TWIN.replace('fact_inbound_shipment.', 'f.')}
        ), s AS (
          SELECT o.id, sum(t.quantity) sq, count(*) ns,
                 bool_or(coalesce(t.order_line,'') = coalesce(o.o_line,'')) any_same_line
          FROM o JOIN fact_inbound_shipment t
            ON t.tenant_id=o.tenant_id AND lower(t.line_state)='shipped'
           AND lower(trim(coalesce(t.operating_unit,'')))=o.ou AND lower(trim(t.order_no))=o.ord AND lower(trim(t.item_code))=o.item
          GROUP BY o.id
        )
        SELECT count(*) pairs,
               count(*) FILTER (WHERE o.oq = s.sq) open_eq_shipped,
               count(*) FILTER (WHERE o.oq < s.sq) open_lt_shipped,
               count(*) FILTER (WHERE o.oq > s.sq) open_gt_shipped,
               count(*) FILTER (WHERE s.ns > 1) multi_shipped_twins,
               count(*) FILTER (WHERE s.any_same_line) same_order_line,
               coalesce(sum(o.oq),0) open_q, coalesce(sum(s.sq),0) shipped_q,
               coalesce(sum(o.oq) FILTER (WHERE o.oq > s.sq),0) open_q_where_gt
        FROM o JOIN s USING (id)
    """,
    "open_rows_with_pod_any": "SELECT count(*) FROM fact_inbound_shipment WHERE lower(line_state)='open_order' AND pod_date IS NOT NULL",
    "arrived_twin_opens": """
        SELECT count(*) FROM fact_inbound_shipment f WHERE lower(f.line_state)='open_order'
          AND trim(coalesce(f.order_no,''))<>'' AND trim(coalesce(f.item_code,''))<>''
          AND EXISTS (SELECT 1 FROM fact_inbound_shipment a WHERE a.tenant_id=f.tenant_id AND a.id<>f.id
            AND lower(a.line_state)='arrived'
            AND lower(trim(coalesce(a.operating_unit,'')))=lower(trim(coalesce(f.operating_unit,'')))
            AND lower(trim(a.order_no))=lower(trim(f.order_no)) AND lower(trim(a.item_code))=lower(trim(f.item_code)))
    """,
    # Reader impact: units counted twice where the reader does not exclude
    "impact_brief_inbound_open_lines": f"SELECT count(*) FROM fact_inbound_shipment WHERE status <> 'received' AND {OPEN_TWIN}",
    "impact_lineup_quarter_pipeline_units": f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE pod_date IS NULL AND {OPEN_TWIN}",
    "impact_lineup_quarter_with_po": f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE pod_date IS NULL AND purchase_order_id IS NOT NULL AND {OPEN_TWIN}",
    "impact_current_incoming_scheduled_no_pod": f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE status='scheduled' AND pod_date IS NULL AND {OPEN_TWIN}",
    "impact_landed_readers_pod_not_null": f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE pod_date IS NOT NULL AND {OPEN_TWIN}",
    "impact_mac_po_price_qty": f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE purchase_order_id IS NOT NULL AND unit_price > 0 AND quantity > 0 AND {OPEN_TWIN}",
    "impact_attribution_resolved_dist": f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment WHERE resolved_distributor_id IS NOT NULL AND product_id IS NOT NULL AND {OPEN_TWIN}",
    "impact_eta_shift_with_evidence": f"SELECT count(*) FROM fact_inbound_shipment WHERE status='scheduled' AND pod_date IS NULL AND shipment_evidence_line_id IS NOT NULL AND {OPEN_TWIN}",
}

out: dict[str, object] = {}
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    out["current_database"] = c.execute(text("SELECT current_database()")).scalar()
    print("current_database =", out["current_database"], flush=True)
    for k, sql in Q.items():
        rows = c.execute(text(sql)).mappings().all()
        out[k] = [{kk: (float(v) if hasattr(v, "as_integer_ratio") and not isinstance(v, int) else v) for kk, v in r.items()} for r in rows]
    c.rollback()
print(json.dumps(out, indent=1, default=str))
