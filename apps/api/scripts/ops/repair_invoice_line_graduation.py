#!/usr/bin/env python3
"""Preview and repair invoice-line mint graduation on cip (destructive-class).

Usage:
  cd apps/api && PYTHONPATH=. python scripts/ops/repair_invoice_line_graduation.py preview
  cd apps/api && PYTHONPATH=. python scripts/ops/repair_invoice_line_graduation.py apply --clone cip_planD_smoke
  cd apps/api && PYTHONPATH=. python scripts/ops/repair_invoice_line_graduation.py apply --cip
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.services.data_integrity_audit import check_invoice_line_graduation_gap
from app.services.imports.shipment_invoice_graduation import (
    preview_invoice_line_graduation,
    refresh_shipment_evidence_current_view,
    repair_all_invoice_graduations,
)


def _db_name(url: str) -> str:
    if not url or "://" not in url:
        return ""
    path = urlparse(url.replace("+psycopg", "").replace("+asyncpg", "")).path
    return path.lstrip("/").split("?")[0]


def _assert_not_cip_urls(*urls: str) -> None:
    for u in urls:
        if _db_name(u) == "cip":
            raise SystemExit("STOP: resolved URL targets cip — use --cip only for production repair")


def _admin_engine(db_name: str):
    admin_url = os.environ.get(
        "SMOKE_ADMIN_URL",
        "postgresql+psycopg://postgres:Exarkun4252%21@127.0.0.1:5432/postgres",
    )
    if db_name:
        base = admin_url.rsplit("/", 1)[0]
        admin_url = f"{base}/{db_name}"
    return create_engine(admin_url, isolation_level="AUTOCOMMIT")


def _resolve_clone_session(clone_name: str) -> Session:
    settings = get_settings()
    sync_url = os.environ.get("DATABASE_URL_SYNC") or settings.database_url_sync
    migrate_url = os.environ.get("DATABASE_URL_SYNC_MIGRATE") or settings.database_url_sync_migrate
    print("DATABASE_URL_SYNC ->", _db_name(sync_url))
    print("DATABASE_URL_SYNC_MIGRATE ->", _db_name(migrate_url))
    _assert_not_cip_urls(sync_url, migrate_url)
    if _db_name(sync_url) != clone_name:
        raise SystemExit(f"DATABASE_URL_SYNC must point to clone {clone_name!r}")
    engine = create_engine(sync_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    dbname = db.scalar(text("SELECT current_database()"))
    if dbname != clone_name:
        raise SystemExit(f"STOP: current_database()={dbname!r}")
    return db


def _resolve_cip_session() -> Session:
    from app.db.session_sync import SessionLocal

    db = SessionLocal()
    dbname = db.scalar(text("SELECT current_database()"))
    if dbname != "cip":
        raise SystemExit(f"STOP: current_database()={dbname!r}, expected cip")
    return db


def _post_apply_assertions(db: Session, repair: dict) -> None:
    audit = check_invoice_line_graduation_gap(db, sample_limit=5)
    gaps = audit.count
    partials = int(audit.meta.get("partial_graduation_worklist") or 0)
    view_count = int(db.scalar(text("SELECT count(*) FROM shipment_evidence_current")) or 0)
    fact_count = int(db.scalar(text("SELECT count(*) FROM fact_inbound_shipment")) or 0)
    print(f"\npost-apply: graduation_gaps={gaps} partial_worklist={partials}")
    print(f"shipment_evidence_current rows={view_count}")
    print(f"fact_inbound_shipment rows={fact_count} (must be unchanged)")
    if gaps != 0:
        raise SystemExit(f"GATE FAIL: {gaps} ungraduated lineages remain")
    drop = repair.get("view_row_drop")
    expected = repair.get("expected_view_drop")
    if drop is not None and expected is not None and drop != expected:
        print(f"WARN: view drop {drop} != expected graduated obs {expected}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoice-line graduation preview/repair")
    parser.add_argument("mode", choices=["preview", "apply"])
    parser.add_argument("--clone", metavar="DB_NAME", help="Apply on disposable clone (template cip)")
    parser.add_argument("--cip", action="store_true", help="Apply on cip (requires explicit flag)")
    args = parser.parse_args()

    if args.mode == "preview":
        db = _resolve_cip_session()
        try:
            report = preview_invoice_line_graduation(db)
            print(json.dumps(report, indent=2, default=str))
            print(
                f"\nSummary: {report['lineages_total']} lineages, "
                f"full={report['full_graduation']} partial={report['partial_graduation']}, "
                f"double_count_units={report['total_double_count_units']}"
            )
        finally:
            db.close()
        return

    if args.cip and args.clone:
        raise SystemExit("Use either --cip or --clone, not both")
    if not args.cip and not args.clone:
        raise SystemExit("apply requires --clone DB_NAME or --cip")

    if args.clone:
        db = _resolve_clone_session(args.clone)
    else:
        db = _resolve_cip_session()

    try:
        preview = preview_invoice_line_graduation(db)
        print("Pre-repair preview:", json.dumps({
            "lineages_total": preview["lineages_total"],
            "full_graduation": preview["full_graduation"],
            "partial_graduation": preview["partial_graduation"],
            "total_double_count_units": preview["total_double_count_units"],
        }))
        dbname = str(db.scalar(text("SELECT current_database()")))
        fact_before = int(db.scalar(text("SELECT count(*) FROM fact_inbound_shipment")) or 0)
        repair = repair_all_invoice_graduations(
            db, dry_run=False, admin_engine=_admin_engine(dbname)
        )
        db.commit()
        fact_after = int(db.scalar(text("SELECT count(*) FROM fact_inbound_shipment")) or 0)
        if fact_before != fact_after:
            raise SystemExit(f"GATE FAIL: fact row count changed {fact_before} -> {fact_after}")
        print("Repair result:", json.dumps(repair, indent=2, default=str))
        _post_apply_assertions(db, repair)
        audit = check_invoice_line_graduation_gap(db, sample_limit=3)
        print("Audit:", json.dumps({
            "check": audit.check,
            "count": audit.count,
            "meta": audit.meta,
        }, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
