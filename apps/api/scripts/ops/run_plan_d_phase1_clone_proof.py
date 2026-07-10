#!/usr/bin/env python3
"""Plan D Phase 1 clone proof — run against cip_planD_smoke only.

Usage (from apps/api):
  set DATABASE_URL_SYNC=postgresql+psycopg://cip:cip@127.0.0.1:5432/cip_planD_smoke
  set DATABASE_URL_SYNC_MIGRATE=postgresql+psycopg://postgres:...@127.0.0.1:5432/cip_planD_smoke
  PYTHONPATH=. python scripts/ops/run_plan_d_phase1_clone_proof.py
"""

from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.services.imports.shipment_plan_d_cutover import (
    assert_database_is,
    backfill_observations_for_jobs,
    open_order_shipped_fact_double_count_diagnostic,
    remigrate_observation_line_identity_keys,
    run_phase1_gate_assertions,
)


def _resolved_urls() -> tuple[str, str]:
    sync = os.environ.get("DATABASE_URL_SYNC", "")
    migrate = os.environ.get("DATABASE_URL_SYNC_MIGRATE", sync)
    print("resolved DATABASE_URL_SYNC:", sync)
    print("resolved DATABASE_URL_SYNC_MIGRATE:", migrate)
    for label, url in ("DATABASE_URL_SYNC", sync), ("DATABASE_URL_SYNC_MIGRATE", migrate):
        dbname = url.rsplit("/", 1)[-1].split("?")[0]
        if dbname == "cip":
            raise SystemExit(f"STOP: {label} resolves to cip — clone override required")
    return sync, migrate


def _ensure_clone_db(*, recreate: bool = False) -> None:
    db_name = os.environ.get("PLAN_D_SMOKE_DB", "cip_planD_smoke")
    admin = os.environ.get(
        "SMOKE_ADMIN_URL",
        "postgresql+psycopg://postgres:Exarkun4252%21@127.0.0.1:5432/postgres",
    )
    from sqlalchemy import create_engine

    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        ).first()
        if exists and recreate:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :n AND pid <> pg_backend_pid()
                    """
                ),
                {"n": db_name},
            )
            conn.execute(text(f'DROP DATABASE "{db_name}"'))
            exists = None
        if exists:
            print(f"{db_name} already exists — using existing clone")
            return
        conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = 'cip' AND pid <> pg_backend_pid()
                """
            )
        )
        conn.execute(text(f'CREATE DATABASE "{db_name}" WITH TEMPLATE cip OWNER cip'))
        print(f"created {db_name} FROM TEMPLATE cip")
        check = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}).first()
        if not check:
            raise RuntimeError(f"clone database {db_name} not found after create")


def _run_alembic_upgrade() -> None:
    from functools import lru_cache

    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    get_settings.cache_clear()
    api_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg = Config(os.path.join(api_root, "alembic.ini"))
    settings = get_settings()
    url = settings.database_url_sync_migrate or settings.database_url_sync
    print("alembic target URL:", url)
    command.upgrade(cfg, "head")


def _clone_session() -> Session:
    from app.core.config import get_settings
    from app.db.sync_url import resolve_sync_engine_url

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(resolve_sync_engine_url(settings), pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)()


def main() -> int:
    recreate = os.environ.get("PLAN_D_RECREATE_CLONE", "1").strip().lower() in ("1", "true", "yes")
    _ensure_clone_db(recreate=recreate)
    _resolved_urls()

    print("\n=== alembic upgrade head (0066) ===")
    _run_alembic_upgrade()

    with _clone_session() as db:
        assert_database_is(db, os.environ.get("PLAN_D_SMOKE_DB", "cip_planD_smoke"))

        print("\n=== key migration ===")
        key_report = remigrate_observation_line_identity_keys(db)
        db.commit()
        print(json.dumps(key_report.__dict__, indent=2, default=str))

        print("\n=== backfill jobs 153/154 ===")
        backfill = backfill_observations_for_jobs(db)
        db.commit()
        print("rows_added_by_job:", backfill)

        print("\n=== idempotency re-backfill ===")
        backfill2 = backfill_observations_for_jobs(db)
        db.commit()
        if any(v != 0 for v in backfill2.values()):
            print("FAIL: re-backfill added rows", backfill2)
            return 1
        print("re-backfill no-op OK")

        print("\n=== gate assertions ===")
        gate = run_phase1_gate_assertions(db)
        print(json.dumps({"passed": gate.passed, "checks": gate.checks}, indent=2, default=str))
        if not gate.passed:
            return 1

        print("\n=== open-to-shipped fact double-count (diagnostic) ===")
        diag = open_order_shipped_fact_double_count_diagnostic(db)
        print(json.dumps(diag, indent=2))

    print("\nPhase 1 clone proof: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
