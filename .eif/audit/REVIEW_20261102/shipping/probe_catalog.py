"""GOV-008 probe: catalog facts (RLS, owners, grants, policies, roles) on cip_test and cip (cip read-only).

Read-only on both. Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/shipping/probe_catalog.py
"""
import psycopg

TABLES = ("fact_inbound_shipment", "shipment_evidence_line", "shipment_evidence_observation", "port_condition")

Q_RLS = """
SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner) AS owner
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = current_schema() AND c.relname = ANY(%s) ORDER BY 1
"""
Q_POL = """
SELECT tablename, policyname, cmd, permissive, roles, qual, with_check FROM pg_policies
WHERE tablename = ANY(%s) ORDER BY 1, 2
"""
Q_GRANTS = """
SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
FROM information_schema.role_table_grants WHERE table_name = ANY(%s) GROUP BY 1, 2 ORDER BY 1, 2
"""
Q_ROLE = "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
Q_TRIG = """
SELECT event_object_table, trigger_name, event_manipulation FROM information_schema.triggers
WHERE event_object_table = ANY(%s) ORDER BY 1, 2
"""
Q_VER = "SELECT version_num FROM alembic_version"
Q_COLS = """
SELECT table_name, count(*) FILTER (WHERE column_name IN ('on_board_date','port_eta_date','port_ata_date','shipping_method',
 'forwarder_code','origin_hub','ship_way','deliver_port','vessel_name','voyage_no','bill_of_lading_no','container_no')) AS water_cols,
 count(*) FILTER (WHERE column_name IN ('superseded_by_fact_id','superseded_by_key')) AS sup_cols
FROM information_schema.columns WHERE table_name = ANY(%s) AND table_schema = current_schema() GROUP BY 1 ORDER BY 1
"""


def run(dsn: str, label: str, readonly: bool) -> None:
    opts = "-c default_transaction_read_only=on" if readonly else ""
    with psycopg.connect(dsn, options=opts) as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout='60s'")
            print(f"===== {label}")
            for name, q, args in (
                ("role", Q_ROLE, None),
                ("alembic", Q_VER, None),
                ("rls", Q_RLS, (list(TABLES),)),
                ("policies", Q_POL, (list(TABLES),)),
                ("grants", Q_GRANTS, (list(TABLES),)),
                ("triggers", Q_TRIG, (list(TABLES),)),
                ("columns", Q_COLS, (list(TABLES),)),
            ):
                try:
                    cur.execute(q, args) if args else cur.execute(q)
                    print(f"-- {name}")
                    for r in cur.fetchall():
                        print("  ", r)
                except Exception as e:  # noqa: BLE001
                    print(f"-- {name}: ERROR {e}")
                    raise
            if readonly:
                cur.execute("SHOW transaction_read_only")
                print("-- transaction_read_only:", cur.fetchone())


if __name__ == "__main__":
    run("postgresql://cip:cip@localhost:5432/cip_test", "cip_test", readonly=True)
    run("postgresql://cip:cip@localhost:5432/cip", "cip (read-only)", readonly=True)
