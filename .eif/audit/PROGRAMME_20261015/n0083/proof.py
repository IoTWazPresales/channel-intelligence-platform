"""N-0083 proof for 20261015_0039 (fx_daily_rate grants + case rate provenance).

usage (from the repo root, apps/api venv python):
  python proof.py clone     clone cip -> cip_n0083, show the defect, upgrade, round trip, drop the clone
  python proof.py cip       apply 20261015_0039 to cip as the migration role and verify as the app role

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

CLONE = "cip_n0083"
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


def numbers(db: str, label: str) -> dict:
    with psycopg.connect(app_url(db)) as conn:
        q = lambda sql: conn.execute(sql).fetchone()  # noqa: E731
        out = {
            "db": q("select current_database()")[0],
            "user": q("select current_user")[0],
            "rev": q("select version_num from alembic_version")[0],
            "cases": q("select count(*) from cpor_case")[0],
            "booked": q("select count(*) from cpor_case where roe_snapshot > 0")[0],
            "has_booked_cols": q(
                "select count(*) from information_schema.columns where table_name = 'cpor_case' "
                "and column_name in ('fx_booked_source','fx_booked_rate_date','fx_override_reason')"
            )[0],
            "owner": q("select tableowner from pg_tables where tablename = 'fx_daily_rate'")[0],
        }
        for priv in ("SELECT", "INSERT", "UPDATE"):
            out["can_" + priv.lower()] = q(f"select has_table_privilege(current_user, 'fx_daily_rate', '{priv}')")[0]
        out["seq_usage"] = q("select has_sequence_privilege(current_user, 'fx_daily_rate_id_seq', 'USAGE')")[0]
    try:
        with psycopg.connect(app_url(db)) as conn:
            out["rate_rows"] = conn.execute("select count(*) from fx_daily_rate").fetchone()[0]
    except psycopg.errors.InsufficientPrivilege as exc:
        out["rate_rows"] = "denied: " + str(exc).splitlines()[0]
    log(f"- {label}: " + ", ".join(f"{k} {v}" for k, v in out.items()))
    return out


def app_write_probe(db: str, label: str) -> str:
    """Insert one rate as the app role, in a transaction that is rolled back."""
    with psycopg.connect(app_url(db)) as conn:
        who = conn.execute("select current_database(), current_user").fetchone()
        try:
            conn.execute(
                "insert into fx_daily_rate (rate_date, quote_pair, rate, source, fetched_at, is_fallback) "
                "values ('2031-01-01', 'USDZAR', 18.5, 'probe', now(), false)"
            )
            result = "insert ok"
        except psycopg.errors.InsufficientPrivilege as exc:
            result = "denied: " + str(exc).splitlines()[0]
        conn.rollback()
    log(f"- {label} (database {who[0]} as {who[1]}): {result}")
    return result


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


def clone_proof() -> None:
    log("# N-0083 clone proof, 20261015_0039")
    make_clone()
    before = numbers(CLONE, "clone before")
    assert before["rev"] == "20261015_0038", before
    d = app_write_probe(CLONE, "clone before: app role writes fx_daily_rate")
    assert d.startswith("denied"), "defect not reproduced on the clone"
    alembic(CLONE, "upgrade", "head")
    up = numbers(CLONE, "clone after upgrade")
    assert up["rev"] == "20261015_0039" and up["can_insert"] and up["can_update"] and up["seq_usage"]
    assert up["has_booked_cols"] == 3
    assert (up["cases"], up["booked"]) == (before["cases"], before["booked"])
    assert app_write_probe(CLONE, "clone after upgrade: app role writes fx_daily_rate") == "insert ok"
    alembic(CLONE, "downgrade", "-1")
    down = numbers(CLONE, "clone after downgrade")
    assert down["rev"] == "20261015_0038" and down["has_booked_cols"] == 0 and not down["can_insert"]
    assert (down["cases"], down["booked"]) == (before["cases"], before["booked"])
    alembic(CLONE, "upgrade", "head")
    again = numbers(CLONE, "clone after second upgrade")
    assert again["rev"] == "20261015_0039" and again["can_insert"]
    assert (again["cases"], again["booked"]) == (before["cases"], before["booked"])
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log("clone dropped")
    (HERE / "N0083_CLONE_PROOF.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


def cip_apply() -> None:
    log("# N-0083 apply to cip, 20261015_0039")
    before = numbers("cip", "cip before")
    assert before["rev"] == "20261015_0038", before
    alembic("cip", "upgrade", "head")
    after = numbers("cip", "cip after")
    assert after["rev"] == "20261015_0039" and after["can_insert"] and after["can_update"] and after["seq_usage"]
    assert (after["cases"], after["booked"]) == (before["cases"], before["booked"])
    assert app_write_probe("cip", "cip after: app role writes fx_daily_rate (rolled back)") == "insert ok"
    (HERE / "N0083_CIP_APPLY.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"clone": clone_proof, "cip": cip_apply}[sys.argv[1]]()
