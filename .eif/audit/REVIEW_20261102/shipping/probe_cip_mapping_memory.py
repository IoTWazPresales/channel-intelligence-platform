"""GOV-008 probe (cip read-only): saved shipment mapping memory vs the voyage headers; does a saved target shadow a voyage field?"""
import json, psycopg
VOY = ("on_board", "eta_date", "ata_date", "shipping_method", "ship_way", "shipway", "deliver_port", "vessel", "voyage", "container", "forwarder")
with psycopg.connect("postgresql://cip:cip@localhost:5432/cip", options="-c default_transaction_read_only=on") as c:
    with c.transaction():
        cur = c.cursor(); cur.execute("SET LOCAL statement_timeout='60s'")
        cur.execute("""SELECT s.id, s.code, s.column_mapping_memory FROM source_definition s
                       WHERE s.id IN (SELECT DISTINCT source_id FROM import_job WHERE template_slug='inbound_shipments' AND source_id IS NOT NULL)""")
        for sid, code, mem in cur.fetchall():
            mem = mem or {}
            byh = mem.get("by_header_norm") or {}
            print("source", sid, code, "| keys:", sorted(k for k in mem.keys() if k != "by_header_norm"))
            print("  selected_sheet_names:", mem.get("selected_sheet_names"))
            for h, e in sorted(byh.items()):
                if any(v in h for v in VOY):
                    print("   ", h, "->", (e or {}).get("target"))
        cur.execute("""SELECT j.id, j.file_name, j.staged_metadata->>'shipment_mapping_auto', j.field_mapping
                       FROM import_job j WHERE j.id IN (1696, 1697)""")
        for jid, fn, auto, fm in cur.fetchall():
            fm = fm or {}
            print("job", jid, fn, "auto:", auto)
            for h, t in sorted(fm.items()):
                if any(v in h.lower().replace(" ", "_").replace("-", "_") for v in VOY):
                    print("   ", h, "->", t)
