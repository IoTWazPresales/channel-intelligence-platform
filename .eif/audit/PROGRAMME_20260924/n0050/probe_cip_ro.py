"""N-0050 read-only probe of cpor_case / cpor_case_line (default db cip). Usage: probe_cip_ro.py [dbname]"""
import sys

import psycopg

db = sys.argv[1] if len(sys.argv) > 1 else "cip"
conn = psycopg.connect(host="localhost", port=5432, user="cip", password="cip", dbname=db)
conn.read_only = True
cur = conn.cursor()

Q = [
    "select current_database()",
    "select now()::date as today",
    "select version()",
    "select version_num from alembic_version",
    "select conname, pg_get_constraintdef(oid) from pg_constraint where conrelid = 'cpor_case_line'::regclass order by conname",
    "select count(*) as lines, count(*) filter (where distributor_id is null) as null_dist, "
    "count(*) filter (where pod_quarter is null) as null_pod from cpor_case_line",
    "select count(*) as cases, count(*) filter (where window_start is null or window_end is null) as null_window, "
    "count(*) filter (where extract(isodow from window_start) <> 1) as start_not_monday, "
    "count(*) filter (where extract(isodow from window_end) <> 7) as end_not_sunday, "
    "count(*) filter (where extract(isodow from window_start) <> 1 or extract(isodow from window_end) <> 7) as non_aligned, "
    "count(*) filter (where window_end < window_start) as inverted from cpor_case",
    "select count(distinct c.id) as cases_with_lines, "
    "count(distinct c.id) filter (where extract(isodow from c.window_start) <> 1 or extract(isodow from c.window_end) <> 7) as nonaligned_cases_with_lines, "
    "count(l.id) filter (where extract(isodow from c.window_start) <> 1 or extract(isodow from c.window_end) <> 7) as lines_on_nonaligned_cases, "
    "count(l.id) filter (where c.window_start is null or c.window_end is null) as lines_on_null_window_cases "
    "from cpor_case c join cpor_case_line l on l.case_id = c.id",
    "select count(*) as dup_grain_groups from (select case_id, product_id, distributor_id, pod_quarter "
    "from cpor_case_line group by 1,2,3,4 having count(*) > 1) d",
    "select extname from pg_extension order by 1",
    "select conrelid::regclass as child, conname from pg_constraint where confrelid in "
    "('cpor_case'::regclass, 'cpor_case_line'::regclass) and contype = 'f' order by 1, 2",
    "select conrelid::regclass as child_of, confrelid::regclass as parent, conname from pg_constraint "
    "where conrelid in ('cpor_case'::regclass, 'cpor_case_line'::regclass) and contype = 'f' order by 1, 2",
]
for q in Q:
    print("--", q[:150])
    cur.execute(q)
    cols = [d[0] for d in cur.description]
    print(" | ".join(cols))
    for r in cur.fetchall():
        print(" | ".join("" if v is None else str(v) for v in r))
conn.rollback()
conn.close()
