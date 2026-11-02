"""GOV-008 probe (cip read-only): closed rows that readers without a line_state filter still pick up."""
import psycopg
Q = {
 "closed_with_pod (dsi_soh_reconciliation landed sum, channel_ops movement-lens via coalesce(confirm,pod))":
 "SELECT line_state, count(*), round(sum(coalesce(quantity,0))) FROM fact_inbound_shipment WHERE line_state LIKE 'closed_%%' AND pod_date IS NOT NULL GROUP BY 1 ORDER BY 1",
 "closed_with_confirm_or_pod": "SELECT line_state, count(*), round(sum(coalesce(quantity,0))) FROM fact_inbound_shipment WHERE line_state LIKE 'closed_%%' AND coalesce(ship_confirm_date,pod_date) IS NOT NULL GROUP BY 1 ORDER BY 1",
 "cover_distribution_inbound_open_like (pod null, dist+product not null; raw qty, before twin remainder)":
 "SELECT (line_state LIKE 'closed_%%') AS closed, count(*), round(sum(coalesce(quantity,0))) FROM fact_inbound_shipment WHERE tenant_id='default' AND pod_date IS NULL AND distributor_id IS NOT NULL AND product_id IS NOT NULL GROUP BY 1",
 "cpor_intake_rows_like (PO, price>0, qty>0, landing date)":
 "SELECT (line_state LIKE 'closed_%%') AS closed, count(*), round(sum(quantity)) FROM fact_inbound_shipment WHERE purchase_order_id IS NOT NULL AND unit_price>0 AND quantity>0 AND coalesce(pod_date,est_pod_date,erd_date) IS NOT NULL GROUP BY 1",
}
with psycopg.connect("postgresql://cip:cip@localhost:5432/cip", options="-c default_transaction_read_only=on") as c:
    with c.transaction():
        cur = c.cursor(); cur.execute("SET LOCAL statement_timeout='60s'")
        for k, q in Q.items():
            cur.execute(q); print("--", k)
            for r in cur.fetchall(): print("  ", r)
