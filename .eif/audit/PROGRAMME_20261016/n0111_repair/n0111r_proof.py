"""N-0111 repair proof for 20261016_0042 and the repair items.

usage (repo root, apps/api venv python):
  python n0111r_proof.py clone   clone cip -> cip_n0111r, upgrade / downgrade / upgrade with counts,
                                 run n0111r_load.py on the clone, drop the clone
  python n0111r_proof.py cip     apply 20261016_0042 to cip as the migration role (after the clone proof)

Passwords are never printed. Writes N0111R_CLONE_PROOF.md / N0111R_CIP_APPLY.md beside this file.
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

CLONE = "cip_n0111r"
OUT: list[str] = []


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
        has = q("select to_regclass('fact_distributor_line_superseded') is not null")[0]
        n = {
            "db": q("select current_database()")[0],
            "rev": q("select version_num from alembic_version")[0],
            "sellout_rows": q("select count(*) from fact_sales_sellout")[0],
            "sellout_units": str(q("select coalesce(sum(units),0) from fact_sales_sellout")[0]),
            "returns_rows": q("select count(*) from fact_returns")[0],
            "inventory_rows": q("select count(*) from fact_inventory_distributor")[0],
            "dsi_staging_rows": q("select count(*) from import_distributor_si_staging_line")[0],
            "cst_fact_rows": q("select count(*) from fact_customer_sellthrough")[0],
            "cst_units": str(q("select coalesce(sum(units_sold),0) from fact_customer_sellthrough")[0]),
            "superseded_table": has,
            "superseded_rows": q("select count(*) from fact_distributor_line_superseded")[0] if has else None,
        }
    log(f"- {label}: " + ", ".join(f"{k} {v}" for k, v in n.items()))
    return n


KEEP = ("sellout_rows", "sellout_units", "returns_rows", "inventory_rows", "dsi_staging_rows", "cst_fact_rows", "cst_units")


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
    log("\n## Proof load on the clone")
    rc = subprocess.call([sys.executable, str(N0110 / "dbrun.py"), CLONE, "--", "python", str(HERE / "n0111r_load.py")])
    out = HERE / "n0111r_load_output.txt"
    if out.exists():
        OUT.extend(["", out.read_text(encoding="utf-8")])
    if rc != 0:
        log(f"LOAD FAILED rc={rc}; clone {CLONE} kept for inspection")
        (HERE / "N0111R_CLONE_PROOF.md").write_text("# N-0111 repair clone proof (FAILED)\n" + "\n".join(OUT) + "\n", encoding="utf-8")
        raise SystemExit(rc)
    alembic(CLONE, "downgrade", "-1")
    numbers(CLONE, "clone after downgrade with superseded records present (the trail table is dropped)")
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log(f"- clone {CLONE} dropped")
    after = numbers("cip", "cip after (unchanged)")
    log(f"- cip unchanged by the clone proof: {same(src, after) and src['rev'] == after['rev']}")
    (HERE / "N0111R_CLONE_PROOF.md").write_text("# N-0111 repair clone proof\n" + "\n".join(OUT) + "\n", encoding="utf-8")


def apply_cip() -> None:
    before = numbers("cip", "cip before")
    alembic("cip", "upgrade", "head")
    after = numbers("cip", "cip after")
    log(f"- cip counts unchanged by 20261016_0042: {same(before, after)}")
    (HERE / "N0111R_CIP_APPLY.md").write_text("# N-0111 repair: apply 20261016_0042 to cip\n" + "\n".join(OUT) + "\n", encoding="utf-8")


def drop_only() -> None:
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")


if __name__ == "__main__":
    {"clone": clone, "cip": apply_cip, "drop": drop_only}[sys.argv[1]]()
