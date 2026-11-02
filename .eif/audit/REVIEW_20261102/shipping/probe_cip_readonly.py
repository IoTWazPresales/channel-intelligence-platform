"""GOV-008 probe: read-only measurements on cip (default_transaction_read_only=on, statement_timeout 60s).

Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/shipping/probe_cip_readonly.py
"""
import psycopg

DSN = "postgresql://cip:cip@localhost:5432/cip"

QUERIES = {
    "tenants_in_fact": "SELECT tenant_id, count(*) FROM fact_inbound_shipment GROUP BY 1 ORDER BY 1",
    "line_state_counts": "SELECT line_state, count(*), round(sum(coalesce(quantity,0))) FROM fact_inbound_shipment GROUP BY 1 ORDER BY 1",
    # Item 7: closed rows a reader without a line_state filter would still count.
    "closed_with_ship_confirm (semantic 'shipped quantity' + channel_ops movement-lens count these)": """
        SELECT line_state, count(*), round(sum(coalesce(quantity,0))) AS qty
        FROM fact_inbound_shipment
        WHERE line_state IN ('closed_shipped','closed_disappeared','closed_moved','closed_superseded')
          AND ship_confirm_date IS NOT NULL GROUP BY 1 ORDER BY 1""",
    "closed_pod_null_with_dist_and_product (channel_ops /cover-distribution inbound_open counts these)": """
        SELECT line_state, count(*), round(sum(coalesce(quantity,0))) AS qty
        FROM fact_inbound_shipment
        WHERE line_state IN ('closed_shipped','closed_disappeared','closed_moved','closed_superseded')
          AND pod_date IS NULL AND distributor_id IS NOT NULL AND product_id IS NOT NULL GROUP BY 1 ORDER BY 1""",
    "closed_superseded_by_origin (0050 downgrade resets ALL of these to 'shipped')": """
        SELECT CASE WHEN superseded_by_key LIKE 'ship:%%' THEN 'po_less_twin (was shipped)'
                    ELSE 'orphan_open (was open_order)' END AS origin,
               count(*), round(sum(coalesce(quantity,0))) AS qty,
               count(*) FILTER (WHERE purchase_order_id IS NOT NULL) AS with_po,
               count(*) FILTER (WHERE ship_confirm_date IS NULL) AS no_confirm
        FROM fact_inbound_shipment WHERE line_state = 'closed_superseded' GROUP BY 1 ORDER BY 1""",
    "superseded_pointer_dangling": """
        SELECT count(*) FILTER (WHERE k.id IS NULL) AS dangling, count(*) AS total
        FROM fact_inbound_shipment f LEFT JOIN fact_inbound_shipment k ON k.id = f.superseded_by_fact_id
        WHERE f.line_state = 'closed_superseded'""",
    "superseded_target_itself_closed": """
        SELECT k.line_state, count(*) FROM fact_inbound_shipment f JOIN fact_inbound_shipment k ON k.id = f.superseded_by_fact_id
        WHERE f.line_state = 'closed_superseded' GROUP BY 1 ORDER BY 1""",
    "open_order_without_evidence_line_by_job (orphans remaining)": """
        SELECT import_job_id, report_type, count(*), round(sum(coalesce(quantity,0)))
        FROM fact_inbound_shipment WHERE lower(line_state) = 'open_order' AND shipment_evidence_line_id IS NULL
        GROUP BY 1, 2 ORDER BY 1, 2""",
    "open_shipped_sheet_old_vs_new_key (blank-invoice grain)": """
        SELECT CASE WHEN source_key LIKE '%%|ord:%%' THEN 'new ord: key' ELSE 'old key' END AS key_shape,
               coalesce(btrim(invoice_line),'') = '' AS blank_invoice, import_job_id, count(*), round(sum(coalesce(quantity,0)))
        FROM fact_inbound_shipment
        WHERE lower(line_state) = 'open_order' AND report_type = 'acza_workbook_shipped'
        GROUP BY 1, 2, 3 ORDER BY 3, 1, 2""",
    "possible_double_open (same OU+order+line+item open twice on Shipped sheet, any key)": """
        SELECT count(*) AS groups, coalesce(sum(n),0) AS rows FROM (
          SELECT tenant_id, operating_unit, order_no, order_line, item_code, delivery_no, count(*) AS n
          FROM fact_inbound_shipment
          WHERE lower(line_state) = 'open_order' AND report_type = 'acza_workbook_shipped'
            AND coalesce(btrim(order_no),'') <> ''
          GROUP BY 1,2,3,4,5,6 HAVING count(*) > 1) g""",
    "jobs_report_date_shape": """
        SELECT j.id, j.status, j.tenant_id, j.file_name,
               (SELECT count(*) FROM regexp_matches(j.file_name, '20[0-9]{6}', 'g')) AS date_tokens,
               (SELECT string_agg(DISTINCT coalesce(l.operating_unit,'<null>') || '/' || l.report_type, ', ')
                  FROM shipment_evidence_line l WHERE l.import_job_id = j.id) AS ou_report_types
        FROM import_job j WHERE j.template_slug = 'inbound_shipments'
        ORDER BY j.id DESC LIMIT 25""",
    "latest_report_date_per_ou_scope": """
        WITH d AS (
          SELECT j.id, j.tenant_id, l.report_type, coalesce(l.operating_unit,'') AS ou,
                 (SELECT CASE WHEN count(*) = 1 THEN to_date((array_agg(m[1]))[1], 'YYYYMMDD') END
                    FROM regexp_matches(j.file_name, '20[0-9]{6}', 'g') m) AS rd
          FROM import_job j JOIN shipment_evidence_line l ON l.import_job_id = j.id
          WHERE j.status = 'completed' AND j.template_slug = 'inbound_shipments')
        SELECT tenant_id, report_type, ou, max(rd), count(DISTINCT id) FROM d GROUP BY 1,2,3 ORDER BY 1,2,3""",
    "po_less_shipped_remaining_with_po_twin_qty_differs": """
        SELECT count(*) FROM fact_inbound_shipment o
        WHERE o.line_state = 'shipped' AND o.purchase_order_id IS NULL
          AND EXISTS (SELECT 1 FROM fact_inbound_shipment s WHERE s.tenant_id = o.tenant_id AND s.id <> o.id
              AND s.line_state = 'shipped' AND s.purchase_order_id IS NOT NULL AND s.delivery_no = o.delivery_no
              AND s.item_code = o.item_code AND s.operating_unit IS NOT DISTINCT FROM o.operating_unit
              AND coalesce(s.import_job_id,0) > coalesce(o.import_job_id,0))""",
    "port_condition_rows": "SELECT tenant_id, port_code, count(*) FROM port_condition GROUP BY 1,2 ORDER BY 1,2",
    "observation_identity_key_cross_tenant_collisions": """
        SELECT count(*) FROM (
          SELECT o.line_identity_key FROM shipment_evidence_observation o JOIN import_job j ON j.id = o.import_job_id
          GROUP BY 1 HAVING count(DISTINCT j.tenant_id) > 1) x""",
}


def main() -> None:
    with psycopg.connect(DSN, options="-c default_transaction_read_only=on") as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout='60s'")
            cur.execute("SHOW transaction_read_only")
            print("transaction_read_only =", cur.fetchone()[0])
            for name, q in QUERIES.items():
                print(f"\n-- {name}")
                try:
                    cur.execute("SAVEPOINT s")
                    cur.execute(q)
                    for r in cur.fetchall():
                        print("  ", r)
                    cur.execute("RELEASE SAVEPOINT s")
                except Exception as e:  # noqa: BLE001
                    print("   ERROR", e)
                    cur.execute("ROLLBACK TO SAVEPOINT s")


if __name__ == "__main__":
    main()
