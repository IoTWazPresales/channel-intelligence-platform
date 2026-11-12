"""Untracked. Run one Alembic command against local cip_test only.

Never prints a URL or secret. Refuses any database name other than cip_test
after the database segment is swapped, and refuses a non-loopback host.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API = Path(__file__).resolve().parent
ROOT_ENV = API.parents[3] / "apps" / "api" / ".env"
TARGET = "cip_test"
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _load(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        found[key] = value
    return found


def _dbname(url: str) -> str:
    path = (urlparse(url).path or "").lstrip("/")
    return path.split("/")[0].split("?")[0]


def _loopback(url: str) -> bool:
    return (urlparse(url).hostname or "").lower() in LOOPBACK


def _swap(url: str, label: str) -> str:
    name = _dbname(url)
    if name != "cip":
        raise SystemExit(f"STOP {label} database={name!r} (expected cip before swap)")
    if not _loopback(url):
        raise SystemExit(f"STOP {label} host is not loopback")
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/" + TARGET))


def _safe(exc: BaseException) -> str:
    message = str(exc)
    if "://" in message or "@" in message:
        return type(exc).__name__
    return type(exc).__name__ + ": " + message[:240]


def _guard_urls() -> str:
    if not ROOT_ENV.is_file():
        raise SystemExit("STOP migrate env file missing")
    found = _load(ROOT_ENV)
    migrate = (found.get("DATABASE_URL_SYNC_MIGRATE") or "").strip()
    sync = (found.get("DATABASE_URL_SYNC") or "").strip()
    if not migrate:
        print(
            f"env_bytes={ROOT_ENV.stat().st_size} env_keys={len(found)} "
            f"env_name={ROOT_ENV.name} parent={ROOT_ENV.parent.name}"
        )
        if sync:
            print(f"source_sync_db={_dbname(sync)!r} loopback={_loopback(sync)}")
        else:
            print("source_sync_db=unset")
        names = sorted(
            key
            for key in found
            if any(part in key.upper() for part in ("DATABASE", "POSTGRES", "PG_", "OWNER", "ALEMBIC"))
        )
        print("migrate_url_unset keys=" + ",".join(names))
        print("all_keys=" + ",".join(sorted(found)))
        raise SystemExit("STOP DATABASE_URL_SYNC_MIGRATE unset; cip cannot grant on postgres-owned tables")
    print(f"source_migrate_db={_dbname(migrate)!r} loopback={_loopback(migrate)}")
    if sync:
        print(f"source_sync_db={_dbname(sync)!r} loopback={_loopback(sync)}")
    else:
        print("source_sync_db=unset")
    migrate_url = _swap(migrate, "DATABASE_URL_SYNC_MIGRATE")
    # App-role URL already proven on this machine. Do not reuse a remote sync URL.
    sync_url = "postgresql://cip:cip@127.0.0.1:5432/cip_test"
    if _dbname(migrate_url) != TARGET or _dbname(sync_url) != TARGET:
        raise SystemExit("STOP swapped database is not cip_test")
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@127.0.0.1:5432/cip_test"
    os.environ["DATABASE_URL_SYNC"] = sync_url
    os.environ["DATABASE_URL_SYNC_MIGRATE"] = migrate_url
    os.environ["CIP_SMOKE_MIGRATE"] = "1"
    return migrate_url


def _connect(migrate_url: str):
    from sqlalchemy import create_engine, text

    from app.db.sync_url import sqlalchemy_sync_engine_url

    engine = create_engine(sqlalchemy_sync_engine_url(migrate_url), pool_pre_ping=True)
    conn = engine.connect()
    db = conn.execute(text("select current_database()")).scalar_one()
    user = conn.execute(text("select current_user")).scalar_one()
    print(f"current_database={db} current_user={user}")
    if db != TARGET:
        conn.close()
        engine.dispose()
        raise SystemExit(f"STOP current_database={db}")
    return engine, conn


def _check(conn) -> None:
    from sqlalchemy import text

    rev = conn.execute(text("select version_num from alembic_version")).all()
    print("alembic_version=" + ",".join(str(row[0]) for row in rev))


def _privileges(conn) -> None:
    from sqlalchemy import text

    tables = (
        "dc_served_account",
        "site_candidate",
        "user_customer_account",
        "store_dc_tenant_config",
    )
    privs = ("SELECT", "INSERT", "UPDATE", "DELETE")
    for table in tables:
        for priv in privs:
            ok = conn.execute(
                text("select has_table_privilege('cip', :table, :priv)"),
                {"table": table, "priv": priv},
            ).scalar_one()
            print(f"has_table_privilege cip {table} {priv}={ok}")
    sequences = (
        "dc_served_account_id_seq",
        "site_candidate_id_seq",
        "user_customer_account_id_seq",
    )
    for seq in sequences:
        for priv in ("USAGE", "SELECT"):
            ok = conn.execute(
                text("select has_sequence_privilege('cip', :seq, :priv)"),
                {"seq": seq, "priv": priv},
            ).scalar_one()
            print(f"has_sequence_privilege cip {seq} {priv}={ok}")
    rev = conn.execute(text("select version_num from alembic_version")).all()
    print("alembic_version=" + ",".join(str(row[0]) for row in rev))


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    os.chdir(API)
    if str(API) not in sys.path:
        sys.path.insert(0, str(API))
    migrate_url = _guard_urls()
    if action == "heads":
        from alembic.config import main as alembic_main

        alembic_main(argv=["heads"])
        return
    if action == "sql":
        from alembic.config import main as alembic_main

        alembic_main(argv=["upgrade", "20261104_0057:20261105_0058", "--sql"])
        return
    engine, conn = _connect(migrate_url)
    try:
        if action == "check":
            _check(conn)
            return
        if action == "privileges":
            _privileges(conn)
            return
        if action != "upgrade":
            raise SystemExit(f"STOP unknown action={action}")
        _check(conn)
        conn.close()
        engine.dispose()
        engine = None
        from alembic.config import main as alembic_main

        alembic_main(argv=["upgrade", "head"])
    except SystemExit:
        raise
    except Exception as exc:
        print(_safe(exc))
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
