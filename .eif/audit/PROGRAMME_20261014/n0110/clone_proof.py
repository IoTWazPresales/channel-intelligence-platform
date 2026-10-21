"""N-0110 clone proof for 20261014_0037. Clone cip -> cip_n0110 (pg_dump/pg_restore), upgrade,
downgrade, upgrade, recompute stock positions on the clone, print numbers, drop the clone.
Passwords are never printed. Writes N0110_CLONE_PROOF.md beside this file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
API = HERE.parents[3] / "apps" / "api"
sys.path.insert(0, str(API))
sys.path.insert(0, str(HERE))

import psycopg  # noqa: E402

from n0110_numbers import numbers, url_for  # noqa: E402

PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
CLONE = "cip_n0110"
lines: list[str] = []


def log(text: str) -> None:
    print(text, flush=True)
    lines.append(text)


def pg_env() -> dict[str, str]:
    """Dump and restore as the admin role so every table is readable and owners are kept."""
    p = urlparse(admin_url())
    env = dict(os.environ)
    env.update(
        {"PGHOST": p.hostname or "localhost", "PGPORT": str(p.port or 5432), "PGUSER": p.username or "", "PGPASSWORD": unquote(p.password or "")}
    )
    return env


def admin_url() -> str:
    """Same resolution as the N-0079 / N-0080 clone proofs. Never printed."""
    import importlib.util
    from urllib.parse import quote

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            owner_pw, _ = winreg.QueryValueEx(key, "PG_OWNER")
        if owner_pw:
            p = urlparse(url_for("cip"))
            return f"postgresql://postgres:{quote(str(owner_pw), safe='')}@{p.hostname or '127.0.0.1'}:{p.port or 5432}/postgres"
    except OSError:
        pass
    path = API / "scripts" / "ops" / "prove_open_channel_absorb_clone.py"
    spec = importlib.util.spec_from_file_location("n0110_ops_admin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module._admin_url()).replace("postgresql+psycopg://", "postgresql://")


def admin_exec(sql: str) -> None:
    with psycopg.connect(admin_url(), autocommit=True) as conn:
        who, is_super = conn.execute("select current_user, usesuper from pg_user where usename = current_user").fetchone()
        log(f"  admin step as {who} (superuser {is_super}): {sql}")
        conn.execute(sql)


def alembic(db: str, *args: str) -> None:
    runner = HERE / "dbrun.py"
    rc = subprocess.call([sys.executable, str(runner), db, "--", "python", "-m", "alembic", *args])
    if rc != 0:
        raise SystemExit(f"alembic {args} failed on {db}")


def show(label: str, db: str) -> dict:
    n = numbers(db)
    keep = ("current_database", "rev", "fact_rows", "fact_units", "fact_soh", "fact_soh_rows", "staging_rows",
            "grain_col", "grain_not_null", "position_table", "positions", "compared")
    log(f"- {label}: " + ", ".join(f"{k} {n[k]}" for k in keep if k in n))
    return n


def recompute(db: str) -> None:
    code = (
        "from app.db.session_sync import SessionLocal\n"
        "from app.services.channel_intelligence.customer_stock_gap import recompute_all_customer_stock_positions\n"
        "from sqlalchemy import text\n"
        "with SessionLocal() as s:\n"
        "    print('recompute current_database()=' + s.execute(text('select current_database()')).scalar())\n"
        "    tenants = [r[0] for r in s.execute(text('select distinct tenant_id from fact_customer_sellthrough where reported_soh is not null'))]\n"
        "    for t in tenants:\n"
        "        print('tenant', t, recompute_all_customer_stock_positions(s, tenant_id=t))\n"
        "    s.commit()\n"
    )
    rc = subprocess.call([sys.executable, str(HERE / "dbrun.py"), db, "--", "python", "-c", code])
    if rc != 0:
        raise SystemExit("recompute failed")


def main() -> int:
    env = pg_env()
    src = show("source cip", "cip")
    admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    admin_exec(f"CREATE DATABASE {CLONE} OWNER cip")
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "cip.dump"
        subprocess.run([str(PG_BIN / "pg_dump"), "-Fc", "-d", "cip", "-f", str(dump)], env=env, check=True)
        subprocess.run(
            [str(PG_BIN / "pg_restore"), "-d", CLONE, str(dump)], env=env, check=False
        )
    before = show("clone before", CLONE)
    assert before["rev"] == src["rev"] and before["fact_rows"] == src["fact_rows"]
    alembic(CLONE, "upgrade", "head")
    up = show("clone after upgrade", CLONE)
    alembic(CLONE, "downgrade", "-1")
    down = show("clone after downgrade", CLONE)
    alembic(CLONE, "upgrade", "head")
    show("clone after re-upgrade", CLONE)
    recompute(CLONE)
    after = show("clone after recompute", CLONE)
    same = all(
        up[k] == down[k] == after[k] == src[k] for k in ("fact_rows", "fact_units", "fact_soh", "fact_soh_rows", "staging_rows")
    )
    log(f"- fact and staging numbers unchanged through every step: {same}")
    log(f"- existing rows keep NULL grain: {after.get('grain_not_null') == 0}")
    admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log("- clone dropped; dump removed. CLONE_PROOF " + ("PASS" if same and after.get("grain_not_null") == 0 else "FAIL"))
    (HERE.parent / "N0110_CLONE_PROOF.md").write_text(
        "# N-0110 clone proof for 20261014_0037 (2026-10-14)\n\n"
        f"Clone `{CLONE}` made from `cip` with pg_dump/pg_restore, then dropped.\n\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
