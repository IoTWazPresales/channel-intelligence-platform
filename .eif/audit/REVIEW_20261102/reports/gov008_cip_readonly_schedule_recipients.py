"""GOV-008 2026-11-02: read-only check that cip's enabled schedules still have D-0132-valid recipients.

Prints ids/booleans only (no names or emails). No writes; default_transaction_read_only=on.
"""
import psycopg

with psycopg.connect("postgresql://cip:cip@localhost:5432/cip", options="-c default_transaction_read_only=on") as conn:
    cur = conn.cursor()
    cur.execute("select current_setting('default_transaction_read_only')")
    print("read_only:", cur.fetchone()[0])
    cur.execute("""select s.id, s.tenant_id = r.tenant_id, s.owner_user_id, s.subscriber_user_ids, r.visibility,
                          r.owner_user_id, r.shared_roles, s.last_run_at, s.next_run_at
                   from report_schedule s join saved_report r on r.id = s.saved_report_id where s.enabled""")
    for row in cur.fetchall():
        sid, same_tenant, owner, subs, vis, r_owner, shared, last, nxt = row
        recipients = list(subs or []) or [owner]
        print(f"schedule {sid}: same_tenant={same_tenant} recipients={recipients} report_visibility={vis} "
              f"report_owner={r_owner} shared_roles={shared} last_run={last} next_run={nxt}")
        for rid in recipients:
            cur.execute("select a.is_active, a.tenant_id = (select tenant_id from report_schedule where id=%s), a.role "
                        "from app_user a where a.id=%s", (sid, rid))
            print(f"  recipient {rid}: (is_active, same_tenant, role) = {cur.fetchone()}")
    cur.execute("""select d.trigger, d.status, left(d.subject, 12), d.created_at from report_delivery d
                   where d.saved_report_id is not null order by d.created_at desc limit 6""")
    print("latest saved-report deliveries (trigger, status, subject prefix, created):")
    for row in cur.fetchall():
        print("  ", row)
