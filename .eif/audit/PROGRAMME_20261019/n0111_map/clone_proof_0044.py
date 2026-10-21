"""N-0111 mapping slots: clone proof for 20261019_0044, then apply to cip and cip_test.

usage (API venv python, from the repo root):
  python clone_proof_0044.py clone      clone cip -> cip_n0111m, upgrade / downgrade / upgrade with printed counts, drop the clone
  python clone_proof_0044.py cip        apply 20261019_0044 to cip as the migration role (after the clone proof)
  python clone_proof_0044.py cip_test   apply 20261019_0044 to cip_test

Passwords are never printed. Writes N0111M_CLONE_PROOF.md / N0111M_<db>_APPLY.md beside this file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
N0110 = ROOT / ".eif" / "audit" / "PROGRAMME_20261014" / "n0110"
sys.path.insert(0, str(N0110))
os.chdir(ROOT / "apps" / "api")
sys.path.insert(0, os.getcwd())

import psycopg  # noqa: E402

import clone_proof as cp  # noqa: E402

from app.core.config import get_settings  # noqa: E402

CLONE = "cip_n0111m"
OUT: list[str] = []
NEW_COLUMNS = (
    "raw_part_number_token",
    "raw_barcode_token",
    "raw_sales_model_token",
    "product_match_tier",
    "product_identifier_check",
)


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
        cols = conn.execute(
            "select column_name from information_schema.columns where table_name='import_customer_sellthrough_staging_line'"
        ).fetchall()
        have = {c[0] for c in cols}
        n = {
            "db": q("select current_database()")[0],
            "rev": q("select version_num from alembic_version")[0],
            "staging_rows": q("select count(*) from import_customer_sellthrough_staging_line")[0],
            "cst_fact_rows": q("select count(*) from fact_customer_sellthrough")[0],
            "cst_units": str(q("select coalesce(sum(units_sold),0) from fact_customer_sellthrough")[0]),
            "cst_onhand": str(q("select coalesce(sum(reported_soh),0) from fact_customer_sellthrough")[0]),
            "cst_superseded": q("select count(*) from fact_customer_sellthrough_superseded")[0],
            "import_jobs": q("select count(*) from import_job")[0],
            "layouts": q("select count(*) from customer_sellthrough_layout")[0],
            "sources": q("select count(*) from source_definition")[0],
            "new_columns_present": sum(1 for c in NEW_COLUMNS if c in have),
        }
        if "product_match_tier" in have:
            n["rows_with_new_values"] = q(
                "select count(*) from import_customer_sellthrough_staging_line where raw_part_number_token is not null "
                "or raw_barcode_token is not null or raw_sales_model_token is not null or product_match_tier is not null "
                "or product_identifier_check is not null"
            )[0]
    log(f"- {label}: " + ", ".join(f"{k} {v}" for k, v in n.items()))
    return n


KEEP = ("staging_rows", "cst_fact_rows", "cst_units", "cst_onhand", "cst_superseded", "import_jobs", "layouts", "sources")


def same(a: dict, b: dict) -> bool:
    return all(a[k] == b[k] for k in KEEP)


def alembic(db: str, *args: str) -> None:
    s = get_settings()
    env = dict(os.environ)
    env["DATABASE_URL"] = swap(s.database_url, db)
    env["DATABASE_URL_SYNC"] = swap(s.database_url_sync, db)
    env["DATABASE_URL_SYNC_MIGRATE"] = admin_db(db)
    with psycopg.connect(env["DATABASE_URL_SYNC_MIGRATE"]) as conn:
        who = conn.execute(
            "select current_database(), current_user, usesuper from pg_user where usename = current_user"
        ).fetchone()
    log(f"  alembic {' '.join(args)} on database {who[0]} as {who[1]} (superuser {who[2]})")
    rc = subprocess.call([sys.executable, "-m", "alembic", *args], env=env)
    if rc != 0:
        raise SystemExit(f"alembic {args} failed on {db}")


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
    round_trip = same(before, up) and same(up, down) and same(down, up2)
    log(f"- round trip keeps every count: {round_trip}")
    log(f"- all five columns present after upgrade: {up['new_columns_present'] == 5}; none after downgrade: {down['new_columns_present'] == 0}")
    log(f"- existing rows carry no new value (all NULL): {up2.get('rows_with_new_values') == 0}")
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log(f"- clone {CLONE} dropped")
    final = numbers("cip", "cip after (unchanged)")
    log(f"- cip unchanged by the clone proof: {same(src, final) and src['rev'] == final['rev']}")
    ok = round_trip and up["new_columns_present"] == 5 and down["new_columns_present"] == 0 and up2.get("rows_with_new_values") == 0
    log("CLONE_PROOF " + ("PASS" if ok else "FAIL"))
    (HERE / "N0111M_CLONE_PROOF.md").write_text(
        "# N-0111 mapping slots: clone proof for 20261019_0044 (2026-10-19)\n\n"
        f"Clone `{CLONE}` made from `cip` with pg_dump/pg_restore, then dropped.\n\n" + "\n".join(OUT) + "\n",
        encoding="utf-8",
    )
    raise SystemExit(0 if ok else 1)


def apply_db(db: str) -> None:
    before = numbers(db, f"{db} before")
    alembic(db, "upgrade", "head")
    after = numbers(db, f"{db} after")
    log(f"- {db} counts unchanged by 20261019_0044: {same(before, after)}; revision now {after['rev']}")
    (HERE / f"N0111M_{db}_APPLY.md").write_text(
        f"# N-0111 mapping slots: apply 20261019_0044 to {db} (2026-10-19)\n\n" + "\n".join(OUT) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "clone":
        clone()
    elif cmd in ("cip", "cip_test"):
        apply_db(cmd)
