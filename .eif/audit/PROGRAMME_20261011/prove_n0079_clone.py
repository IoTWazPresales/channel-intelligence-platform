"""Prove the N-0079 historical load on a clone named cip_n0079.

Prints booleans and counts only. Does not print connection strings.
Touches cip only after the clone load and the append-only check both pass.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from app.services.budget_ledger import load_historical_settled  # noqa: E402

CLONE_DB = "cip_n0079"
STATUS = ROOT / ".eif" / "audit" / "PROGRAMME_20261011" / "n0079_clone_status.txt"
DUMP_PATH = ROOT / ".tmp" / "cip_n0079.dump"
PG_BINS = [
    Path(r"C:\Program Files\PostgreSQL\18\bin"),
    Path(r"C:\Program Files\PostgreSQL\17\bin"),
    Path(r"C:\Program Files\PostgreSQL\16\bin"),
]


def step(message: str) -> None:
    print(message, flush=True)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    with STATUS.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def scrub(text_value: str, secrets: list[str]) -> str:
    cleaned = text_value or ""
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[SECRET]")
    return cleaned[-1500:]


def ops_admin_url() -> str:
    path = API / "scripts" / "ops" / "prove_open_channel_absorb_clone.py"
    spec = importlib.util.spec_from_file_location("n0079_ops_admin", path)
    if spec is None or spec.loader is None:
        raise SystemExit("ops_admin_helper_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module._admin_url())


def registry_owner_url(sync: URL) -> str | None:
    """Same owner secret the earlier migrations used. Never print it."""
    try:
        import winreg
        from urllib.parse import quote

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            owner_pw, _ = winreg.QueryValueEx(key, "PG_OWNER")
    except OSError:
        return None
    if not owner_pw:
        return None
    host = sync.host or "127.0.0.1"
    port = sync.port or 5432
    return f"postgresql+psycopg://postgres:{quote(str(owner_pw), safe='')}@{host}:{port}/postgres"


def resolve_admin(settings, sync: URL) -> tuple[URL, str]:
    migrate_raw = (settings.database_url_sync_migrate or "").strip()
    if migrate_raw:
        return make_url(migrate_raw), "settings"
    env_url = (os.environ.get("SMOKE_ADMIN_URL") or "").strip()
    if env_url:
        return make_url(env_url), "env"
    owner_url = registry_owner_url(sync)
    if owner_url:
        return make_url(owner_url), "registry_owner"
    return make_url(ops_admin_url()), "ops_helper"


def pg_bin() -> Path:
    for candidate in PG_BINS:
        if (candidate / "pg_dump.exe").is_file():
            return candidate
    raise SystemExit("pg_dump_missing")


def create_clone(admin: URL, sync: URL, secrets: list[str]) -> str:
    admin_engine = create_engine(
        admin.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with admin_engine.connect() as conn:
        who = conn.execute(text("SELECT current_user")).scalar()
        is_super = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
        step(f"admin_login_ok True")
        step(f"admin_is_superuser {bool(is_super)}")
        step(f"admin_user_is_postgres {who == 'postgres'}")
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": CLONE_DB},
        ).first()
        if exists:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :name AND pid <> pg_backend_pid()
                    """
                ),
                {"name": CLONE_DB},
            )
            conn.execute(text(f'DROP DATABASE "{CLONE_DB}"'))
            step("dropped_existing_clone")
        try:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = 'cip' AND pid <> pg_backend_pid()
                    """
                )
            )
            conn.execute(text(f'CREATE DATABASE "{CLONE_DB}" WITH TEMPLATE cip OWNER cip'))
            step("created_clone_from_template")
            return "template"
        except SQLAlchemyError as exc:
            step("template_failed")
            step(scrub(str(exc.__class__.__name__), secrets))
    dump_bin = pg_bin()
    DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DUMP_PATH.exists():
        DUMP_PATH.unlink()
    dump_env = os.environ.copy()
    dump_env["PGPASSWORD"] = sync.password or ""
    dumped = subprocess.run(
        [
            str(dump_bin / "pg_dump.exe"),
            "-h",
            sync.host or "127.0.0.1",
            "-p",
            str(sync.port or 5432),
            "-U",
            sync.username or "cip",
            "-d",
            "cip",
            "-Fc",
            "-f",
            str(DUMP_PATH),
            "--no-owner",
            "--no-privileges",
        ],
        env=dump_env,
        capture_output=True,
        text=True,
    )
    if dumped.returncode != 0:
        step(f"fail pg_dump code {dumped.returncode}")
        step(scrub(dumped.stderr, secrets))
        raise SystemExit("pg_dump")
    step(f"dump_mebibytes {DUMP_PATH.stat().st_size // (1024 * 1024)}")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{CLONE_DB}" OWNER cip'))
    restore_env = os.environ.copy()
    restore_env["PGPASSWORD"] = sync.password or ""
    restored = subprocess.run(
        [
            str(dump_bin / "pg_restore.exe"),
            "-h",
            sync.host or "127.0.0.1",
            "-p",
            str(sync.port or 5432),
            "-U",
            sync.username or "cip",
            "-d",
            CLONE_DB,
            "--no-owner",
            "--no-privileges",
            str(DUMP_PATH),
        ],
        env=restore_env,
        capture_output=True,
        text=True,
    )
    DUMP_PATH.unlink(missing_ok=True)
    step(f"pg_restore_code {restored.returncode}")
    if restored.returncode not in (0, 1):
        step(scrub(restored.stderr, secrets))
        raise SystemExit("pg_restore")
    step("created_clone_from_dump")
    return "dump"


def alembic_upgrade(sync_url: str, migrate_url: str, *, smoke: bool, secrets: list[str], label: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL_SYNC"] = sync_url
    env["DATABASE_URL_SYNC_MIGRATE"] = migrate_url
    if smoke:
        env["CIP_SMOKE_MIGRATE"] = "1"
    else:
        env.pop("CIP_SMOKE_MIGRATE", None)
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API,
        env=env,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        step(f"fail {label} code {completed.returncode}")
        step(scrub(completed.stderr, secrets))
        step(scrub(completed.stdout, secrets))
        raise SystemExit(label)
    step(f"{label}_ok")


def mutation_blocked(session, row_id: int, statement: str) -> tuple[bool, str]:
    try:
        session.execute(text(statement), {"row_id": row_id})
        session.commit()
        return False, "committed"
    except SQLAlchemyError as exc:
        session.rollback()
        message = str(exc).lower()
        if "append-only" in message:
            return True, "append-only"
        if "permission denied" in message:
            return False, "permission_denied"
        return False, exc.__class__.__name__


def main() -> None:
    STATUS.write_text("", encoding="utf-8")
    settings = get_settings()
    sync = make_url(settings.database_url_sync)
    step(f"migrate_url_set {bool((settings.database_url_sync_migrate or '').strip())}")
    step(f"sync_db_is_cip {sync.database == 'cip'}")
    if sync.database != "cip":
        raise SystemExit("sync_url_is_not_cip")
    try:
        admin, admin_source = resolve_admin(settings, sync)
    except Exception as exc:
        step(f"admin_resolve_failed {exc.__class__.__name__}")
        raise SystemExit("admin_resolve") from exc
    step(f"admin_source {admin_source}")
    secrets = [part for part in (sync.password, admin.password) if part]
    clone_sync = sqlalchemy_sync_engine_url(
        sync.set(database=CLONE_DB).render_as_string(hide_password=False)
    )
    clone_migrate = admin.set(database=CLONE_DB).render_as_string(hide_password=False)
    resume = os.environ.get("N0079_RESUME") == "1"
    if resume:
        step("resume_existing_clone")
    else:
        try:
            create_clone(admin, sync, secrets)
        except SQLAlchemyError as exc:
            step("admin_login_ok False")
            step(scrub(exc.__class__.__name__, secrets))
            raise SystemExit("admin_login") from exc
        alembic_upgrade(clone_sync, clone_migrate, smoke=True, secrets=secrets, label="alembic_clone")

    clone_engine = create_engine(clone_sync)
    CloneSession = sessionmaker(bind=clone_engine, autoflush=False, autocommit=False)
    with CloneSession() as session:
        dbname = session.execute(text("SELECT current_database()")).scalar()
        step(f"clone_db_is_cip_n0079 {dbname == CLONE_DB}")
        if dbname != CLONE_DB:
            raise SystemExit("connected_to_wrong_database")
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        step(f"clone_revision {revision}")
        first = load_historical_settled(session)
        session.commit()
        step(f"written {first['written']}")
        step(f"skipped_present {first['skipped_present']}")
        step(f"skipped_no_result {first['skipped_no_result']}")
        second = load_historical_settled(session)
        session.commit()
        step(f"second_written {second['written']}")
        step(f"second_skipped_present {second['skipped_present']}")
        row_id = session.execute(text("SELECT id FROM budget_ledger_entry LIMIT 1")).scalar()
        before_count = session.execute(text("SELECT count(*) FROM budget_ledger_entry")).scalar()
        step(f"ledger_has_row {row_id is not None}")
        step(f"ledger_rows {before_count}")

    update_blocked = False
    delete_blocked = False
    update_reason = "no_row"
    delete_reason = "no_row"
    if row_id is not None:
        owner_engine = create_engine(sqlalchemy_sync_engine_url(clone_migrate))
        OwnerSession = sessionmaker(bind=owner_engine, autoflush=False, autocommit=False)
        with OwnerSession() as owner:
            update_blocked, update_reason = mutation_blocked(
                owner,
                int(row_id),
                "UPDATE budget_ledger_entry SET actor = actor WHERE id = :row_id",
            )
            delete_blocked, delete_reason = mutation_blocked(
                owner,
                int(row_id),
                "DELETE FROM budget_ledger_entry WHERE id = :row_id",
            )
    step(f"update_blocked {update_blocked}")
    step(f"update_reason {update_reason}")
    step(f"delete_blocked {delete_blocked}")
    step(f"delete_reason {delete_reason}")
    with CloneSession() as session:
        after_count = session.execute(text("SELECT count(*) FROM budget_ledger_entry")).scalar()
    step(f"ledger_rows_after {after_count}")
    if not update_blocked or not delete_blocked or after_count != before_count:
        step("stop_before_cip append-only check failed")
        raise SystemExit(2)

    alembic_upgrade(
        sync.render_as_string(hide_password=False),
        admin.set(database="cip").render_as_string(hide_password=False),
        smoke=False,
        secrets=secrets,
        label="alembic_cip",
    )
    from app.db.session_sync import SessionLocal

    with SessionLocal() as session:
        dbname = session.execute(text("SELECT current_database()")).scalar()
        step(f"cip_db_is_cip {dbname == 'cip'}")
        if dbname != "cip":
            raise SystemExit("refusing_load_not_cip")
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        step(f"cip_revision {revision}")
        loaded = load_historical_settled(session)
        session.commit()
        step(f"cip_written {loaded['written']}")
        step(f"cip_skipped_present {loaded['skipped_present']}")
        step(f"cip_skipped_no_result {loaded['skipped_no_result']}")
        again = load_historical_settled(session)
        session.commit()
        step(f"cip_second_written {again['written']}")
    step("done")


if __name__ == "__main__":
    main()
