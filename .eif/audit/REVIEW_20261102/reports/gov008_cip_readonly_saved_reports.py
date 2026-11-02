"""GOV-008 2026-11-02: read-only inventory of saved reports / schedules on cip (no writes, no values)."""
import psycopg

with psycopg.connect("postgresql://cip:cip@localhost:5432/cip", options="-c default_transaction_read_only=on") as conn:
    cur = conn.cursor()
    cur.execute("select current_database(), current_setting('default_transaction_read_only')")
    print("db/read_only:", cur.fetchone())
    cur.execute("""select r.id, r.metric_key, r.grains, r.period_grain,
                          r.definition_v2 is not null as has_v2,
                          (r.definition_v2 ? 'migrated_from') as migrated,
                          coalesce((r.definition_v2->>'v1_equivalent')::boolean, null) as v1eq,
                          (select count(*) from report_schedule s where s.saved_report_id=r.id and s.enabled) as enabled_schedules
                   from saved_report r order by r.id""")
    print("id | metric | grains | period_grain | has_v2 | migrated | v1_equivalent | enabled_schedules")
    for row in cur.fetchall():
        print(" | ".join(str(x) for x in row))
    cur.execute("select count(*), count(*) filter (where definition_v2 ? 'migrated_from') from dashboard_widget")
    print("dashboard_widget total / migrated:", cur.fetchone())
    cur.execute("select cadence, enabled, count(*) from report_schedule group by 1,2 order by 1,2")
    print("schedules by cadence/enabled:", cur.fetchall())
