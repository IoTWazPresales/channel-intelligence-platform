#!/usr/bin/env python3
"""Plan D Phase 2 cutover on cip (approved writes after clone proof)."""

from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.services.imports.shipment_plan_d_cutover import (
    assert_database_is,
    backfill_observations_for_jobs,
    remigrate_observation_line_identity_keys,
    run_phase1_gate_assertions,
)


def _resolved_urls() -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    sync = os.environ.get("DATABASE_URL_SYNC") or settings.database_url_sync
    migrate = (
        os.environ.get("DATABASE_URL_SYNC_MIGRATE")
        or settings.database_url_sync_migrate
        or sync
    )
    print("resolved DATABASE_URL_SYNC:", sync)
    print("resolved DATABASE_URL_SYNC_MIGRATE:", migrate)
    dbname = sync.rsplit("/", 1)[-1].split("?")[0]
    if dbname != "cip":
        raise SystemExit(f"STOP: expected cip, got {dbname!r}")


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    get_settings.cache_clear()
    api_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg = Config(os.path.join(api_root, "alembic.ini"))
    settings = get_settings()
    print("alembic target URL:", settings.database_url_sync_migrate or settings.database_url_sync)
    command.upgrade(cfg, "head")


def _session() -> Session:
    from app.core.config import get_settings
    from app.db.sync_url import resolve_sync_engine_url

    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(resolve_sync_engine_url(settings), pool_pre_ping=True)
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)()


def main() -> int:
    _resolved_urls()
    print("\n=== alembic upgrade head (0066) ===")
    _run_alembic_upgrade()

    with _session() as db:
        assert_database_is(db, "cip")

        print("\n=== observation key migration ===")
        key_report = remigrate_observation_line_identity_keys(db)
        db.commit()
        print(json.dumps(key_report.__dict__, indent=2, default=str))

        print("\n=== backfill jobs 153/154 ===")
        backfill = backfill_observations_for_jobs(db)
        db.commit()
        print("rows_added_by_job:", backfill)

        gate = run_phase1_gate_assertions(db)
        print(json.dumps({"passed": gate.passed, "checks": gate.checks}, indent=2, default=str))
        if not gate.passed:
            return 1

        from app.core.feature_flags import (
            shipment_bitemporal_dual_write_enabled,
            shipment_bitemporal_read_enabled,
        )

        print("dual_write_enabled:", shipment_bitemporal_dual_write_enabled())
        print("read_enabled:", shipment_bitemporal_read_enabled())

        can_read_view = db.scalar(text("SELECT count(*) FROM shipment_evidence_current"))
        print("shipment_evidence_current readable, rows:", int(can_read_view or 0))

    print("\nPhase 2 cip cutover: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
