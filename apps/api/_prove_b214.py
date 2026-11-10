"""Disposable-database proof for BACKLOG-214. Not part of the commit.

The app role on the existing local cluster cannot create a database, and that
cluster's superuser password is not available. This starts a throwaway cluster
on port 55432, creates cip_backlog214_empty there, and never connects to cip.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

DISPOSABLE = "cip_backlog214_empty"
PORT = "55432"
API = Path(__file__).resolve().parent
CLUSTER = API.parent.parent / ".pg_b214"
PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
PY = Path(r"C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe")


def _pg(name: str) -> Path:
    path = PG_BIN / name
    if not path.exists():
        raise SystemExit(f"missing {path}")
    return path


def ensure_cluster() -> None:
    initdb = _pg("initdb.exe")
    pg_ctl = _pg("pg_ctl.exe")
    if not (CLUSTER / "PG_VERSION").exists():
        CLUSTER.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [str(initdb), "-D", str(CLUSTER), "-U", "postgres", "-A", "trust", "--encoding=UTF8", "--locale=C"],
            check=True,
        )
    status = subprocess.run([str(pg_ctl), "status", "-D", str(CLUSTER)], capture_output=True, text=True)
    if status.returncode == 0:
        print("cluster_already_running", flush=True)
        return
    log = CLUSTER / "server.log"
    subprocess.run(
        [str(pg_ctl), "start", "-D", str(CLUSTER), "-l", str(log), "-w", "-o", f"-p {PORT}"],
        check=True,
    )


def main() -> int:
    ensure_cluster()
    maintenance = make_url(f"postgresql+psycopg://postgres@127.0.0.1:{PORT}/postgres")
    maint_engine = create_engine(maintenance, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with maint_engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
        print(f"maintenance_current_database={current}", flush=True)
        if current != "postgres":
            raise SystemExit(f"maintenance connection is {current}, not postgres")
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                    CREATE ROLE cip LOGIN;
                  END IF;
                END $$;
                """
            )
        )
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": DISPOSABLE},
        ).scalar()
        if exists:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": DISPOSABLE},
            )
            conn.execute(text(f'DROP DATABASE "{DISPOSABLE}"'))
            print(f"dropped_previous={DISPOSABLE}", flush=True)
        conn.execute(text(f'CREATE DATABASE "{DISPOSABLE}"'))
        print(f"created={DISPOSABLE}", flush=True)
    maint_engine.dispose()

    target = maintenance.set(database=DISPOSABLE)
    target_engine = create_engine(target, pool_pre_ping=True)
    with target_engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
        print(f"current_database={current}", flush=True)
        if current != DISPOSABLE:
            raise SystemExit(f"refusing to migrate {current}")
    target_engine.dispose()

    env = os.environ.copy()
    raw = target.render_as_string(hide_password=False)
    env["DATABASE_URL_SYNC"] = raw
    env["DATABASE_URL_SYNC_MIGRATE"] = raw
    env["CIP_SMOKE_MIGRATE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    command = [str(PY), "-m", "alembic", *sys.argv[1:]]
    print(f"alembic_cwd={API}", flush=True)
    print("alembic_target_database=" + DISPOSABLE, flush=True)
    completed = subprocess.run(command, cwd=API, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
