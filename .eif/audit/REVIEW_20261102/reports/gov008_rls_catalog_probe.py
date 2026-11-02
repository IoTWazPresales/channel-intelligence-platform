"""GOV-008 2026-11-02: read-only catalog probe of RLS flags on cip_test (and cip, read-only)."""
import sys
import psycopg

TABLES = ["dashboard", "dashboard_widget", "saved_report", "cpor_case", "cpor_case_line",
          "report_schedule", "report_delivery", "fact_sales_sellout", "dim_product", "dim_customer", "app_user"]
for db in sys.argv[1:]:
    with psycopg.connect(f"postgresql://cip:cip@localhost:5432/{db}", options="-c default_transaction_read_only=on") as conn:
        cur = conn.cursor()
        cur.execute("select current_database(), current_user, current_setting('default_transaction_read_only')")
        print("db/user/read_only:", cur.fetchone())
        cur.execute("select rolsuper, rolbypassrls from pg_roles where rolname=current_user")
        print("rolsuper/rolbypassrls:", cur.fetchone())
        cur.execute("""select c.relname, c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner),
                              (select count(*) from pg_policies p where p.tablename=c.relname and p.schemaname='public')
                       from pg_class c join pg_namespace n on n.oid=c.relnamespace
                       where n.nspname='public' and c.relname = any(%s) order by 1""", (TABLES,))
        print("table | rls | force | owner | policies")
        for r in cur.fetchall():
            print(" | ".join(str(x) for x in r))
        cur.execute("select version_num from alembic_version")
        print("alembic:", cur.fetchall())
        cur.execute("""select tablename, policyname, qual from pg_policies
                       where schemaname='public' and tablename in ('cpor_case_line','fact_sales_sellout') order by 1,2""")
        for r in cur.fetchall():
            print("policy:", r[0], r[1], (r[2] or "")[:220])
        print()
