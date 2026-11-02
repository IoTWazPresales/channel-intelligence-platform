"""GOV-008 probe (cip read-only): shipped facts of one OU+delivery+item under two different non-null POs, written by different jobs."""
import psycopg
Q = """
SELECT count(*) AS groups, sum(n) AS rows, round(sum(q)) AS qty FROM (
  SELECT f.operating_unit, f.delivery_no, f.item_code, count(*) n, count(DISTINCT f.purchase_order_id) pos,
         count(DISTINCT f.import_job_id) jobs, sum(f.quantity) q
  FROM fact_inbound_shipment f
  WHERE f.tenant_id = 'default' AND f.line_state = 'shipped' AND f.purchase_order_id IS NOT NULL AND coalesce(btrim(f.delivery_no),'') <> ''
  GROUP BY 1,2,3 HAVING count(DISTINCT f.purchase_order_id) > 1 AND count(DISTINCT f.import_job_id) > 1) g
"""
Q2 = Q.replace("count(DISTINCT f.import_job_id) > 1", "max(f.import_job_id) <> min(f.import_job_id) AND bool_or(f.import_job_id = (SELECT max(id) FROM import_job WHERE template_slug='inbound_shipments' AND status='completed')) = false")
with psycopg.connect("postgresql://cip:cip@localhost:5432/cip", options="-c default_transaction_read_only=on") as c:
    with c.transaction():
        cur = c.cursor(); cur.execute("SET LOCAL statement_timeout='60s'")
        cur.execute(Q); print("delivery+item under >1 PO across >1 job:", cur.fetchone())
        cur.execute("""SELECT f.delivery_no, f.item_code, f.purchase_order_id, f.import_job_id, f.quantity FROM fact_inbound_shipment f
                       WHERE f.tenant_id='default' AND f.line_state='shipped' AND f.purchase_order_id IS NOT NULL AND (f.operating_unit, f.delivery_no, f.item_code) IN (
                         SELECT operating_unit, delivery_no, item_code FROM fact_inbound_shipment WHERE tenant_id='default' AND line_state='shipped'
                           AND purchase_order_id IS NOT NULL GROUP BY 1,2,3 HAVING count(DISTINCT purchase_order_id) > 1 AND count(DISTINCT import_job_id) > 1)
                       ORDER BY 1,2,4 LIMIT 12""")
        for r in cur.fetchall(): print("  ", r)
