"""N-0050 proof: 20260924_0023 on cip_test only.

Phase A (scratch schema n0050_scratch inside cip_test): copy cpor_case + cpor_case_line
from cip (read-only COPY out), with an alembic_version at 20260906_0022, then
upgrade -> numbers -> supersede probe -> downgrade refusal -> downgrade -> numbers
-> upgrade -> numbers. Scratch schema dropped at the end (copied rows removed).
Phase B (cip_test.public): upgrade -> downgrade -> upgrade on the test fixtures;
left at 20260924_0023.

Never writes to cip; prints current_database() before every write. No credentials printed.
"""
import io
import os
import subprocess
import sys

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
PY = os.path.join(ROOT, "apps", "api", ".venv", "Scripts", "python.exe")
DRIVER = os.path.join(HERE, "run_alembic_cip_test.py")
SCHEMA = "n0050_scratch"
CONN = dict(host="localhost", port=5432, user="cip", password="cip")

src = psycopg.connect(dbname="cip", **CONN)
src.read_only = True
dst = psycopg.connect(dbname="cip_test", autocommit=True, **CONN)


def one(conn, sql, *a):
    with conn.cursor() as cur:
        cur.execute(sql, a or None)
        return cur.fetchone()


def rows(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def show(conn, title, sql):
    cols, rs = rows(conn, sql)
    print(f"  [{title}]")
    print("   ", " | ".join(cols))
    for r in rs:
        print("   ", " | ".join("" if v is None else str(v) for v in r))


def guard_write(conn, label):
    db = one(conn, "select current_database()")[0]
    print(f"current_database() = {db}   (before write: {label})")
    if db != "cip_test":
        raise SystemExit("refusing write outside cip_test")


def alembic(schema, *args):
    cmd = [PY, DRIVER] + (["--schema", schema] if schema else []) + list(args)
    print(f"$ alembic {' '.join(args)}   (cip_test, search_path={schema or 'public'})")
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    for ln in out:
        if "Running" in ln or "current_database" in ln or "Error" in ln or "refused" in ln:
            print("   ", ln)
    return r.returncode, "\n".join(out)


def numbers(conn, sch, phase):
    t = f"{sch}.cpor_case_line"
    c = f"{sch}.cpor_case"
    print(f"== numbers: {phase} ({sch})")
    show(conn, "row counts", f"select (select count(*) from {c}) as cases, (select count(*) from {t}) as lines")
    has = one(
        conn,
        "select count(*) from information_schema.columns where table_schema=%s and table_name='cpor_case_line' "
        "and column_name in ('window_start','window_end')",
        sch,
    )[0]
    print(f"  window columns present on cpor_case_line: {has}")
    show(
        conn,
        "uq_cpor_case_line_grain",
        f"select conname, pg_get_constraintdef(oid) as def from pg_constraint where conrelid = '{t}'::regclass "
        "and contype in ('u','c') and conname not like '%not_null' order by conname",
    )
    if has == 2:
        show(
            conn,
            "window backfill",
            f"select count(*) as lines, count(l.window_start) as ws_populated, count(l.window_end) as we_populated, "
            f"count(*) filter (where l.window_start = k.window_start and l.window_end = k.window_end) as eq_case_window, "
            f"count(*) filter (where extract(isodow from l.window_start) <> 1 or extract(isodow from l.window_end) <> 7) "
            f"as lines_not_week_aligned_flagged, "
            f"count(distinct l.case_id) filter (where extract(isodow from l.window_start) <> 1 "
            f"or extract(isodow from l.window_end) <> 7) as cases_not_week_aligned "
            f"from {t} l join {c} k on k.id = l.case_id",
        )
        show(
            conn,
            "unique violations on new grain (must be 0; NULL keys are distinct in PG, so only all-non-NULL keys can violate)",
            f"select count(*) filter (where not has_null) as violating_groups, "
            f"count(*) filter (where has_null) as null_key_dup_groups_allowed "
            f"from (select case_id, product_id, distributor_id, pod_quarter, window_start, "
            f"bool_or(distributor_id is null or pod_quarter is null) as has_null "
            f"from {t} group by 1,2,3,4,5 having count(*) > 1) d",
        )
    show(
        conn,
        "old-grain groups with >1 row (NULL pod_quarter; pre-existing)",
        f"select count(*) as groups from (select case_id, product_id, distributor_id, pod_quarter from {t} "
        f"group by 1,2,3,4 having count(*) > 1) d",
    )
    show(conn, "alembic_version", f"select version_num from {sch}.alembic_version")


# ---------------------------------------------------------------- phase A
print("######## PHASE A: scratch copy of cip cpor_case + cpor_case_line inside cip_test")
print("source:", one(src, "select current_database()")[0], "(read-only session)")
show(src, "cip today (read-only)", "select now()::date as today, (select version_num from alembic_version) as rev, "
     "(select count(*) from cpor_case) as cases, (select count(*) from cpor_case_line) as lines")

guard_write(dst, "create scratch schema")
dst.execute(f"drop schema if exists {SCHEMA} cascade")
dst.execute(f"create schema {SCHEMA}")
for tbl in ("cpor_case", "cpor_case_line"):
    dst.execute(f"create table {SCHEMA}.{tbl} (like public.{tbl} including defaults including constraints)")
dst.execute(f"alter table {SCHEMA}.cpor_case add constraint pk_cpor_case primary key (id)")
dst.execute(f"alter table {SCHEMA}.cpor_case_line add constraint pk_cpor_case_line primary key (id)")
dst.execute(
    f"alter table {SCHEMA}.cpor_case_line add constraint uq_cpor_case_line_grain "
    "unique (case_id, product_id, distributor_id, pod_quarter)"
)
dst.execute(
    f"alter table {SCHEMA}.cpor_case_line add constraint fk_cpor_case_line_case_id_cpor_case "
    f"foreign key (case_id) references {SCHEMA}.cpor_case(id)"
)
dst.execute(f"create table {SCHEMA}.alembic_version (version_num varchar(32) primary key)")
dst.execute(f"insert into {SCHEMA}.alembic_version values ('20260906_0022')")

for tbl in ("cpor_case", "cpor_case_line"):
    cols = rows(src, f"select * from {tbl} limit 0")[0]
    collist = ", ".join(cols)
    buf = io.BytesIO()
    with src.cursor() as cur:
        with cur.copy(f"copy (select {collist} from {tbl} order by id) to stdout") as cp:
            for chunk in cp:
                buf.write(chunk)
    guard_write(dst, f"copy {tbl} into {SCHEMA}")
    with dst.cursor() as cur:
        with cur.copy(f"copy {SCHEMA}.{tbl} ({collist}) from stdin") as cp:
            cp.write(buf.getvalue())
src.rollback()

numbers(dst, SCHEMA, "A0 before upgrade (at 20260906_0022)")

guard_write(dst, "alembic upgrade head (scratch)")
rc, _ = alembic(SCHEMA, "upgrade", "head")
print("  rc =", rc)
numbers(dst, SCHEMA, "A1 after upgrade")

# supersede probe: same (case, product, distributor, pod_quarter) with a later window must now store
guard_write(dst, "supersede probe insert")
probe = one(
    dst,
    f"select l.id, l.case_id, l.window_start, l.window_end from {SCHEMA}.cpor_case_line l "
    f"where l.window_end - l.window_start >= 13 and l.pod_quarter is not null order by l.id limit 1",
)
lid, cid, ws, we = probe
with dst.cursor() as cur:
    cur.execute(
        f"insert into {SCHEMA}.cpor_case_line (id, case_id, product_id, distributor_id, pod_quarter, srp, vat_rate, "
        f"dealer_margin_pct, margin_source, estimate_qty, window_start, window_end, created_at, updated_at) "
        f"select id + 1000000, case_id, product_id, distributor_id, pod_quarter, srp, vat_rate, dealer_margin_pct, margin_source, "
        f"0, window_start + 7, window_end, now(), now() from {SCHEMA}.cpor_case_line where id = %s returning id",
        (lid,),
    )
    new_id = cur.fetchone()[0]
print(f"  supersede probe: line {lid} (case {cid}, {ws}..{we}) + successor line {new_id} from {ws}+7 -> stored OK")
try:
    with dst.cursor() as cur:
        cur.execute(
            f"insert into {SCHEMA}.cpor_case_line (id, case_id, product_id, distributor_id, pod_quarter, srp, vat_rate, "
            f"dealer_margin_pct, margin_source, estimate_qty, window_start, window_end, created_at, updated_at) "
            f"select id + 2000000, case_id, product_id, distributor_id, pod_quarter, srp, vat_rate, dealer_margin_pct, margin_source, "
            f"0, window_start, window_end, now(), now() from {SCHEMA}.cpor_case_line where id = %s",
            (lid,),
        )
    print("  duplicate same-window insert: UNEXPECTEDLY ACCEPTED")
except psycopg.errors.UniqueViolation:
    print("  duplicate same-window insert: rejected by uq_cpor_case_line_grain (expected)")
rc, out = alembic(SCHEMA, "downgrade", "20260906_0022")
print("  downgrade with two windows for one grain: rc =", rc, "->", "refused" if "downgrade refused" in out else "NOT refused")
guard_write(dst, "remove supersede probe row")
dst.execute(f"delete from {SCHEMA}.cpor_case_line where id = %s", (new_id,))
print(f"  probe row {new_id} deleted")

guard_write(dst, "alembic downgrade 20260906_0022 (scratch)")
rc, _ = alembic(SCHEMA, "downgrade", "20260906_0022")
print("  rc =", rc)
numbers(dst, SCHEMA, "A2 after downgrade")

guard_write(dst, "alembic upgrade head again (scratch)")
rc, _ = alembic(SCHEMA, "upgrade", "head")
print("  rc =", rc)
numbers(dst, SCHEMA, "A3 after re-upgrade")

guard_write(dst, "drop scratch schema (removes copied rows)")
dst.execute(f"drop schema {SCHEMA} cascade")
print("  exists after drop:", one(dst, "select count(*) from pg_namespace where nspname=%s", SCHEMA)[0])

# ---------------------------------------------------------------- phase B
print("######## PHASE B: cip_test.public (test fixtures)")
numbers(dst, "public", "B0 before")
guard_write(dst, "alembic upgrade head (public)")
print("  rc =", alembic(None, "upgrade", "head")[0])
numbers(dst, "public", "B1 after upgrade")
guard_write(dst, "alembic downgrade 20260906_0022 (public)")
print("  rc =", alembic(None, "downgrade", "20260906_0022")[0])
numbers(dst, "public", "B2 after downgrade")
guard_write(dst, "alembic upgrade head again (public)")
print("  rc =", alembic(None, "upgrade", "head")[0])
numbers(dst, "public", "B3 final (left at head)")

src.close()
dst.close()
