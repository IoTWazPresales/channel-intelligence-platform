"""N-0111 layouts: clone proof for 20261016_0043 and for the source -> layout migration.

usage (repo root, apps/api venv python):
  python n0111l_proof.py clone   clone cip -> cip_n0111l, upgrade / downgrade / upgrade with counts,
                                 dry run + apply + second apply of the source migration on the clone,
                                 downgrade with layouts present, drop the clone
  python n0111l_proof.py cip     apply 20261016_0043 to cip as the migration role (after the clone proof)
  python n0111l_proof.py cip_test   apply 20261016_0043 to cip_test
  python n0111l_proof.py migrate-cip  run the source migration on cip (--apply --expect-db cip)

Passwords are never printed. Writes N0111L_CLONE_PROOF.md / N0111L_CIP_APPLY.md beside this file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

HERE = Path(__file__).resolve().parent
N0110 = HERE.parents[1] / "PROGRAMME_20261014" / "n0110"
sys.path.insert(0, str(N0110))
os.chdir(HERE.parents[3] / "apps" / "api")

import psycopg  # noqa: E402

import clone_proof as cp  # noqa: E402

from app.core.config import get_settings  # noqa: E402

CLONE = "cip_n0111l"
OUT: list[str] = []
MIGRATE = HERE.parents[3] / "apps" / "api" / "scripts" / "ops" / "migrate_cst_sources_to_layouts.py"


def log(s: str) -> None:
    print(s, flush=True)
    OUT.append(s)


def swap(url: str, db: str) -> str:
    return urlunparse(urlparse(url)._replace(path="/" + db))


def admin_db(db: str) -> str:
    return swap(cp.admin_url(), db)


def numbers(db: str, label: str) -> dict:
    with psycopg.connect(admin_db(db)) as conn:
        q = lambda sql: conn.execute(sql).fetchone()  # noqa: E731
        has = q("select to_regclass('customer_sellthrough_layout') is not null")[0]
        hidden_col = q(
            "select count(*) from information_schema.columns where table_name='source_definition' and column_name='is_hidden'"
        )[0]
        n = {
            "db": q("select current_database()")[0],
            "rev": q("select version_num from alembic_version")[0],
            "cst_fact_rows": q("select count(*) from fact_customer_sellthrough")[0],
            "cst_units": str(q("select coalesce(sum(units_sold),0) from fact_customer_sellthrough")[0]),
            "cst_onhand": str(q("select coalesce(sum(reported_soh),0) from fact_customer_sellthrough")[0]),
            "cst_superseded": q("select count(*) from fact_customer_sellthrough_superseded")[0],
            "import_jobs": q("select count(*) from import_job")[0],
            "sources": q("select count(*) from source_definition")[0],
            "sellout_rows": q("select count(*) from fact_sales_sellout")[0],
            "layout_table": has,
            "layouts": q("select count(*) from customer_sellthrough_layout")[0] if has else None,
            "is_hidden_column": bool(hidden_col),
            "sources_hidden": q("select count(*) from source_definition where is_hidden")[0] if hidden_col else None,
        }
    log(f"- {label}: " + ", ".join(f"{k} {v}" for k, v in n.items()))
    return n


KEEP = ("cst_fact_rows", "cst_units", "cst_onhand", "cst_superseded", "import_jobs", "sources", "sellout_rows")


def same(a: dict, b: dict) -> bool:
    return all(a[k] == b[k] for k in KEEP)


def alembic(db: str, *args: str) -> None:
    s = get_settings()
    env = dict(os.environ)
    env["DATABASE_URL"] = swap(s.database_url, db)
    env["DATABASE_URL_SYNC"] = swap(s.database_url_sync, db)
    env["DATABASE_URL_SYNC_MIGRATE"] = admin_db(db)
    with psycopg.connect(env["DATABASE_URL_SYNC_MIGRATE"]) as conn:
        who = conn.execute("select current_database(), current_user, usesuper from pg_user where usename = current_user").fetchone()
    log(f"  alembic {' '.join(args)} on database {who[0]} as {who[1]} (superuser {who[2]})")
    rc = subprocess.call([sys.executable, "-m", "alembic", *args], env=env)
    if rc != 0:
        raise SystemExit(f"alembic {args} failed on {db}")


def migrate(db: str, *extra: str) -> int:
    out = HERE / f"source_migration_{db}.md"
    return subprocess.call(
        [sys.executable, str(N0110 / "dbrun.py"), db, "--", "python", str(MIGRATE), "--out", str(out), *extra]
    )


def clone() -> None:
    src = numbers("cip", "cip (source, read only)")
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    cp.admin_exec(f"CREATE DATABASE {CLONE} OWNER cip")
    env = cp.pg_env()
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "cip.dump"
        subprocess.run([str(cp.PG_BIN / "pg_dump"), "-Fc", "-d", "cip", "-f", str(dump)], env=env, check=True)
        subprocess.run([str(cp.PG_BIN / "pg_restore"), "-d", CLONE, str(dump)], env=env, check=False)
    before = numbers(CLONE, "clone before")
    assert same(src, before) and src["rev"] == before["rev"], "clone differs from cip"
    alembic(CLONE, "upgrade", "head")
    up = numbers(CLONE, "clone after upgrade")
    alembic(CLONE, "downgrade", "-1")
    down = numbers(CLONE, "clone after downgrade")
    alembic(CLONE, "upgrade", "head")
    up2 = numbers(CLONE, "clone after upgrade again")
    log(f"- round trip keeps every count: {same(before, up) and same(up, down) and same(down, up2)}")

    log("\n## Source migration on the clone")
    log("### dry run (writes nothing)")
    rc = migrate(CLONE)
    dry = numbers(CLONE, "clone after dry run")
    log(f"- dry run wrote nothing: {dry['layouts'] == 0 and dry['sources_hidden'] == 0 and same(up2, dry)}")
    dry_file = HERE / f"source_migration_{CLONE}.md"
    if dry_file.exists():
        dry_file.replace(HERE / f"source_migration_{CLONE}_dry_run.md")
    log("### apply (and a second apply)")
    rc = migrate(CLONE, "--apply", "--expect-db", CLONE)
    after = numbers(CLONE, "clone after the migration")
    log(f"- sell-through facts, jobs and sources unchanged by the migration: {same(up2, after)}")
    if rc != 0:
        log(f"MIGRATION FAILED rc={rc}; clone {CLONE} kept for inspection")
        (HERE / "N0111L_CLONE_PROOF.md").write_text("# N-0111 layouts clone proof (FAILED)\n" + "\n".join(OUT) + "\n", encoding="utf-8")
        raise SystemExit(rc)
    alembic(CLONE, "downgrade", "-1")
    down2 = numbers(CLONE, "clone after downgrade with layouts present (the layout table and hide flag are dropped)")
    log(f"- downgrade with layouts present keeps every fact, job and source: {same(up2, down2)}")
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log(f"- clone {CLONE} dropped")
    final = numbers("cip", "cip after (unchanged)")
    log(f"- cip unchanged by the clone proof: {same(src, final) and src['rev'] == final['rev']}")
    (HERE / "N0111L_CLONE_PROOF.md").write_text("# N-0111 layouts clone proof\n" + "\n".join(OUT) + "\n", encoding="utf-8")


def apply_db(db: str, title: str, name: str) -> None:
    before = numbers(db, f"{db} before")
    alembic(db, "upgrade", "head")
    after = numbers(db, f"{db} after")
    log(f"- {db} counts unchanged by 20261016_0043: {same(before, after)}")
    (HERE / name).write_text(f"# {title}\n" + "\n".join(OUT) + "\n", encoding="utf-8")


def drop_only() -> None:
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "clone":
        clone()
    elif cmd == "cip":
        apply_db("cip", "N-0111 layouts: apply 20261016_0043 to cip", "N0111L_CIP_APPLY.md")
    elif cmd == "cip_test":
        apply_db("cip_test", "N-0111 layouts: apply 20261016_0043 to cip_test", "N0111L_CIPTEST_APPLY.md")
    elif cmd == "migrate-cip":
        rc = migrate("cip", "--apply", "--expect-db", "cip")
        numbers("cip", "cip after the source migration")
        raise SystemExit(rc)
    elif cmd == "drop":
        drop_only()
