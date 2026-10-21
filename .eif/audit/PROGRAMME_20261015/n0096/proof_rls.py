"""N-0096 proof for 20261015_0040 (inline product-line RLS on customer_stock_position and
fact_customer_sellthrough_superseded).

usage (from the repo root, apps/api venv python):
  python proof_rls.py clone     clone cip -> cip_n0096, upgrade, round trip, drop the clone
  python proof_rls.py cip       apply 20261015_0040 to cip as the migration role
  python proof_rls.py cip_test  apply 20261015_0040 to cip_test

Passwords are never printed. The clone is dropped at the end of `clone`.
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
from n0110_numbers import url_for  # noqa: E402

from app.core.config import get_settings  # noqa: E402

CLONE = "cip_n0096"
TABLES = ("customer_stock_position", "fact_customer_sellthrough_superseded")
OUT: list[str] = []


def log(text: str) -> None:
    print(text, flush=True)
    OUT.append(text)


def swap(url: str, db: str) -> str:
    return urlunparse(urlparse(url)._replace(path="/" + db))


def admin_db(db: str) -> str:
    return swap(cp.admin_url(), db)


def app_url(db: str) -> str:
    return url_for(db)


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


def make_clone() -> None:
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    cp.admin_exec(f"CREATE DATABASE {CLONE} OWNER cip")
    env = cp.pg_env()
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "cip.dump"
        subprocess.run([str(cp.PG_BIN / "pg_dump"), "-Fc", "-d", "cip", "-f", str(dump)], env=env, check=True)
        subprocess.run([str(cp.PG_BIN / "pg_restore"), "-d", CLONE, str(dump)], env=env, check=False)
    log(f"clone {CLONE} made from cip")


def policies(db: str) -> dict:
    out = {}
    with psycopg.connect(admin_db(db)) as conn:
        for t in TABLES:
            out[t] = conn.execute(
                "select cmd, qual, with_check from pg_policies where tablename = %s order by cmd", (t,)
            ).fetchall()
    return out


def numbers(db: str, label: str) -> dict:
    with psycopg.connect(admin_db(db)) as conn:
        q = lambda sql: conn.execute(sql).fetchone()  # noqa: E731
        out = {
            "db": q("select current_database()")[0],
            "rev": q("select version_num from alembic_version")[0],
            "stock_position_rows": q("select count(*) from customer_stock_position")[0],
            "stock_position_compared": q("select count(*) from customer_stock_position where status = 'compared'")[0],
            "superseded_rows": q("select count(*) from fact_customer_sellthrough_superseded")[0],
            "superseded_units": q("select coalesce(sum(units_sold), 0) from fact_customer_sellthrough_superseded")[0],
        }
    with psycopg.connect(app_url(db)) as conn:
        out["app_role"] = conn.execute("select current_user").fetchone()[0]
        out["app_sees_stock_position"] = conn.execute("select count(*) from customer_stock_position").fetchone()[0]
        out["app_sees_superseded"] = conn.execute("select count(*) from fact_customer_sellthrough_superseded").fetchone()[0]
    log(f"- {label}: " + ", ".join(f"{k} {v}" for k, v in out.items()))
    return out


def show_policies(db: str, label: str) -> dict:
    p = policies(db)
    log(f"- {label}: policy definitions")
    for t, rows in p.items():
        for cmd, qual, chk in rows:
            log(f"    {t} {cmd}: using={qual!r} with_check={chk!r}")
    return p


def counts_equal(a: dict, b: dict) -> bool:
    keys = ("stock_position_rows", "stock_position_compared", "superseded_rows", "superseded_units",
            "app_sees_stock_position", "app_sees_superseded")
    return all(a[k] == b[k] for k in keys)


def clone_proof() -> None:
    log("# N-0096 clone proof, 20261015_0040")
    make_clone()
    before = numbers(CLONE, "clone before")
    assert before["rev"] == "20261015_0039", before
    pol_before = show_policies(CLONE, "clone before")
    assert all("cip_product_id_" in (q or c) for rows in pol_before.values() for _cmd, q, c in rows)
    alembic(CLONE, "upgrade", "head")
    up = numbers(CLONE, "clone after upgrade")
    pol_up = show_policies(CLONE, "clone after upgrade")
    assert up["rev"] == "20261015_0040" and counts_equal(before, up)
    assert all("cip_product_line_" in (q or c) for rows in pol_up.values() for _cmd, q, c in rows)
    assert [c for c, *_ in pol_up["fact_customer_sellthrough_superseded"]] == ["INSERT", "SELECT"]
    assert [c for c, *_ in pol_up["customer_stock_position"]] == ["DELETE", "INSERT", "SELECT", "UPDATE"]
    alembic(CLONE, "downgrade", "-1")
    down = numbers(CLONE, "clone after downgrade")
    pol_down = show_policies(CLONE, "clone after downgrade")
    assert down["rev"] == "20261015_0039" and counts_equal(before, down)
    assert pol_down == pol_before, "downgrade did not restore the original policies"
    alembic(CLONE, "upgrade", "head")
    again = numbers(CLONE, "clone after second upgrade")
    pol_again = show_policies(CLONE, "clone after second upgrade")
    assert again["rev"] == "20261015_0040" and counts_equal(before, again)
    assert pol_again == pol_up, "second upgrade differs from the first"
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log("clone dropped")
    (HERE / "N0096_RLS_CLONE_PROOF.md").write_text(chr(10).join(OUT) + chr(10), encoding="utf-8")


def apply_to(db: str, name: str) -> None:
    log(f"# N-0096 apply 20261015_0040 to {db}")
    before = numbers(db, f"{db} before")
    assert before["db"] == db, before
    assert before["rev"] == "20261015_0039", before
    pol_before = show_policies(db, f"{db} before")
    alembic(db, "upgrade", "head")
    after = numbers(db, f"{db} after")
    pol_after = show_policies(db, f"{db} after")
    assert after["rev"] == "20261015_0040" and counts_equal(before, after)
    assert pol_after != pol_before
    (HERE / name).write_text(chr(10).join(OUT) + chr(10), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "clone":
        clone_proof()
    elif cmd == "cip":
        apply_to("cip", "N0096_RLS_CIP_APPLY.md")
    elif cmd == "cip_test":
        apply_to("cip_test", "N0096_RLS_CIP_TEST_APPLY.md")
