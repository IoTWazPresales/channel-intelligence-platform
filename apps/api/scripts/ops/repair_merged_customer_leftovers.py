#!/usr/bin/env python3
"""Repair leftover FKs on merged customer losers (clone first, cip only with --confirm-cip).

Reuses ``repoint_customer_footprint_full``. Does not mint or promote customers.

Usage (from apps/api, PYTHONPATH=.):
  python scripts/ops/repair_merged_customer_leftovers.py --preview
  python scripts/ops/repair_merged_customer_leftovers.py --clone --recreate-clone
  python scripts/ops/repair_merged_customer_leftovers.py --confirm-cip
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import resolve_sync_engine_url, sqlalchemy_sync_engine_url  # noqa: E402
from app.services.customer_leftover_repair import (  # noqa: E402
    COMPUSPEED_LOSER_ID,
    LeftoverRepairDriftError,
    leftover_row_total_across_merged_losers,
    preview_leftover_repair,
    repair_dirty_losers,
)

CLONE_DB = os.environ.get("CIP_LEFTOVER_REPAIR_SMOKE_DB", "cip_merged_leftover_repair")


def _mask_url(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or ""
    db = (parsed.path or "/").lstrip("/")
    auth = f"{user}:***@" if user else ""
    return f"postgresql://{auth}{host}{port}/{db}"


def _cip_sync_url() -> str:
    return sqlalchemy_sync_engine_url(resolve_sync_engine_url(get_settings()))


def _swap_db(url: str, dbname: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    path = f"/{dbname}"
    swapped = urlunparse(parsed._replace(path=path))
    return sqlalchemy_sync_engine_url(swapped)


def _admin_url() -> str:
    env = (os.environ.get("SMOKE_ADMIN_URL") or "").strip()
    if env:
        return sqlalchemy_sync_engine_url(env)
    # Reuse the existing clone-proof admin URL helper — do not duplicate credentials here.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "prove_open_channel_absorb_clone",
        ROOT / "scripts" / "ops" / "prove_open_channel_absorb_clone.py",
    )
    if spec is None or spec.loader is None:
        raise SystemExit("SMOKE_ADMIN_URL unset and cannot load prove_open_channel_absorb_clone._admin_url")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return sqlalchemy_sync_engine_url(mod._admin_url())


def _print_preview(preview: dict) -> None:
    print(f"current_database() {preview['database']}")
    print(f"merged_loser_count {preview['merged_loser_count']}")
    print(f"dirty_loser_count {preview['dirty_loser_count']}")
    print(f"total_leftover_rows {preview['total_leftover_rows']}")
    print("--- per loser ---")
    for item in preview["losers"]:
        flag = "  [COMPUSPEED unexplained pre-absorb rows]" if item["compuspeed_unexplained"] else ""
        print(
            f"loser {item['loser_id']} {item['loser_code']!r} {item['loser_name']!r} "
            f"-> winner {item['winner_id']} {item['winner_code']!r} {item['winner_name']!r} "
            f"rows={item['row_count']}{flag}"
        )
        for key, n in sorted(item["fk_counts"].items(), key=lambda kv: -int(kv[1])):
            print(f"  {key}: {n}")
    print("--- winner snapshots ---")
    for label, snap in preview["winner_snapshots"].items():
        print(
            f"{label} {snap['customer_id']}: cpor_case={snap['cpor_case']} "
            f"commercial_lineup_line={snap['commercial_lineup_line']} "
            f"fact_customer_sellthrough={snap['fact_customer_sellthrough']}"
        )


def _ensure_clone(*, recreate: bool) -> None:
    engine = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": CLONE_DB}
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
                {"n": CLONE_DB},
            )
            conn.execute(text(f'DROP DATABASE "{CLONE_DB}"'))
            exists = None
        if exists:
            print(f"{CLONE_DB} already exists — using existing clone")
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
        conn.execute(text(f'CREATE DATABASE "{CLONE_DB}" WITH TEMPLATE cip OWNER cip'))
        print(f"created {CLONE_DB} FROM TEMPLATE cip")


def _run_repair(url: str, *, require_audit_match: bool) -> None:
    print("resolved url", _mask_url(url))
    eng = create_engine(url)
    SessionLocal = sessionmaker(bind=eng, class_=Session, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        name = db.execute(text("select current_database()")).scalar()
        print("current_database()", name)
        preview = preview_leftover_repair(db)
        _print_preview(preview)
        before_snaps = dict(preview["winner_snapshots"])
        out = repair_dirty_losers(db, preview=preview, require_audit_match=require_audit_match)
        db.commit()
        leftover_after = leftover_row_total_across_merged_losers(db)
        print("repaired_count", out["repaired_count"])
        for row in out["repaired"]:
            flag = " COMPUSPEED" if row["compuspeed_unexplained"] else ""
            print(f"  repaired loser {row['loser_id']} -> {row['winner_id']}{flag}")
        print("leftover_rows_after", leftover_after)
        print("--- winner snapshots after ---")
        for label, snap in out["winner_snapshots_after"].items():
            before = before_snaps[label]
            print(
                f"{label} {snap['customer_id']}: "
                f"cpor_case {before['cpor_case']} -> {snap['cpor_case']}; "
                f"lineup {before['commercial_lineup_line']} -> {snap['commercial_lineup_line']}; "
                f"cst {before['fact_customer_sellthrough']} -> {snap['fact_customer_sellthrough']}"
            )
        if leftover_after != 0:
            raise SystemExit(f"STOP: leftover_rows_after={leftover_after}")
        print("REPAIR PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--preview", action="store_true")
    p.add_argument("--clone", action="store_true")
    p.add_argument("--recreate-clone", action="store_true")
    p.add_argument("--confirm-cip", action="store_true", help="DANGER: write on live cip after clone PASS")
    args = p.parse_args()
    if not (args.preview or args.clone or args.confirm_cip):
        p.error("specify --preview, --clone, and/or --confirm-cip")

    if args.preview:
        url = _cip_sync_url()
        print("resolved url", _mask_url(url))
        eng = create_engine(url)
        SessionLocal = sessionmaker(bind=eng, class_=Session, autoflush=False, autocommit=False)
        with SessionLocal() as db:
            print("current_database()", db.execute(text("select current_database()")).scalar())
            preview = preview_leftover_repair(db)
            _print_preview(preview)
            try:
                from app.services.customer_leftover_repair import assert_preview_matches_audit

                assert_preview_matches_audit(preview)
                print("audit match 9/3266")
            except LeftoverRepairDriftError as exc:
                print("STOP", exc)
                raise SystemExit(1) from exc
        if not (args.clone or args.confirm_cip):
            return

    if args.clone:
        clone_url = _swap_db(_cip_sync_url(), CLONE_DB)
        dbname = clone_url.rsplit("/", 1)[-1].split("?")[0]
        if dbname == "cip":
            raise SystemExit("STOP: clone URL resolves to cip")
        _ensure_clone(recreate=bool(args.recreate_clone))
        print("clone url", _mask_url(clone_url))
        _run_repair(clone_url, require_audit_match=True)
        print("CLONE PROOF PASS")

    if args.confirm_cip:
        url = _cip_sync_url()
        eng = create_engine(url)
        SessionLocal = sessionmaker(bind=eng, class_=Session, autoflush=False, autocommit=False)
        with SessionLocal() as db:
            name = db.execute(text("select current_database()")).scalar()
            if name != "cip":
                raise SystemExit(f"expected cip, got {name}")
        print("cip url", _mask_url(url))
        _run_repair(url, require_audit_match=True)
        print("CIP REPAIR PASS")


if __name__ == "__main__":
    _ = COMPUSPEED_LOSER_ID
    main()
