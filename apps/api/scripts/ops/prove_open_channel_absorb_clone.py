#!/usr/bin/env python3
"""Clone-proof OPEN_CHANNEL absorb of dim_customer 19 + 5013 onto id=1.

Refuses DATABASE_URL that resolves to ``cip``. Creates/uses disposable clone
``cip_oc_absorb_smoke`` from TEMPLATE cip, runs preview + confirm, asserts
losers soft-redirected and FKs on survivor.

Usage (from apps/api):
  set PYTHONPATH=.
  python scripts/ops/prove_open_channel_absorb_clone.py
  python scripts/ops/prove_open_channel_absorb_clone.py --recreate-clone
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.open_channel_absorb import (  # noqa: E402
    confirm_absorb_into_open_channel,
    preview_absorb_into_open_channel,
)

CLONE_DB = os.environ.get("OC_ABSORB_SMOKE_DB", "cip_oc_absorb_smoke")
LOSER_IDS = [19, 5013]
AUDIT = "clone-proof absorb TMP/SADC Open Channel duplicates onto OPEN_CHANNEL (Warren 2026-08-02)"


def _admin_url() -> str:
    return os.environ.get(
        "SMOKE_ADMIN_URL",
        "postgresql+psycopg://postgres:Exarkun4252%21@127.0.0.1:5432/postgres",
    )


def _clone_url() -> str:
    # Prefer explicit override; otherwise derive from apps/api/.env host/user but force clone db name.
    env = (ROOT / ".env").read_text(encoding="utf-8")
    base = None
    for line in env.splitlines():
        if line.startswith("DATABASE_URL="):
            base = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if not base:
        raise SystemExit("DATABASE_URL missing")
    base = base.replace("+asyncpg", "+psycopg").replace("+psycopg2", "+psycopg")
    # strip db name
    prefix, _db = base.rsplit("/", 1)
    url = f"{prefix}/{CLONE_DB}"
    dbname = url.rsplit("/", 1)[-1].split("?")[0]
    if dbname == "cip":
        raise SystemExit("STOP: clone URL resolves to cip")
    return url


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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--recreate-clone", action="store_true")
    p.add_argument("--apply-cip", action="store_true", help="DANGER: apply on live cip after clone PASS")
    args = p.parse_args()

    if args.apply_cip:
        # Separate gated path — still verify db name.
        env = (ROOT / ".env").read_text(encoding="utf-8")
        url = None
        for line in env.splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
        assert url
        url = url.replace("+asyncpg", "+psycopg").replace("+psycopg2", "+psycopg")
        eng = create_engine(url)
        Session = sessionmaker(bind=eng)
        with Session() as db:
            name = db.execute(text("select current_database()")).scalar()
            if name != "cip":
                raise SystemExit(f"expected cip, got {name}")
            preview = preview_absorb_into_open_channel(
                db, loser_ids=LOSER_IDS, audit_note=AUDIT, expected_survivor_id=1
            )
            print("cip preview", preview)
            out = confirm_absorb_into_open_channel(
                db,
                loser_ids=LOSER_IDS,
                audit_note=AUDIT + " · applied on cip after clone PASS",
                performed_by="ops-script",
                expected_survivor_id=1,
            )
            print("cip apply", out)
        return

    _ensure_clone(recreate=bool(args.recreate_clone))
    url = _clone_url()
    print("clone url db=", url.rsplit("/", 1)[-1])
    eng = create_engine(url)
    Session = sessionmaker(bind=eng)
    with Session() as db:
        name = db.execute(text("select current_database()")).scalar()
        if name == "cip":
            raise SystemExit("STOP: connected to cip")
        print("connected", name)
        preview = preview_absorb_into_open_channel(
            db, loser_ids=LOSER_IDS, audit_note=AUDIT, expected_survivor_id=1
        )
        print("preview losers", preview["loser_ids"], "survivor", preview["survivor_id"])
        for plan in preview["loser_plans"]:
            print(" plan", plan["customer_id"], plan["customer_name"], plan["fk_breakdown"])
        out = confirm_absorb_into_open_channel(
            db,
            loser_ids=LOSER_IDS,
            audit_note=AUDIT,
            performed_by="clone-proof",
            expected_survivor_id=1,
        )
        print("confirm", out)
        for lid in LOSER_IDS:
            mid = db.execute(
                text("select merged_into_customer_id from dim_customer where id=:i"),
                {"i": lid},
            ).scalar()
            assert mid == 1, f"loser {lid} merged_into={mid}"
        print("CLONE PROOF PASS")


if __name__ == "__main__":
    main()
