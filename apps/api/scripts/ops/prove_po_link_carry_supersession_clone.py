#!/usr/bin/env python3
"""Prove PO-link carry on soft-supersession (BACKLOG-118) on a disposable clone.

Refuses DATABASE_URL that resolves to ``cip``. Creates/uses disposable clone
``cip_po_carry_smoke`` from TEMPLATE cip.

Scenarios C2–C6:
  C2 fresh carry
  C3 idempotent re-run
  C4 winner already holds one of loser's POs
  C5 mid-tx failure → full rollback
  C6 active consumers see winner links, not superseded loser

Usage (from apps/api):
  set PYTHONPATH=.
  python scripts/ops/prove_po_link_carry_supersession_clone.py
  python scripts/ops/prove_po_link_carry_supersession_clone.py --recreate-clone
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.models.commercial_lineup import (  # noqa: E402
    CommercialLineupCase,
    CommercialLineupCasePo,
)
from app.models.purchase_order import PurchaseOrder  # noqa: E402
from app.services.commercial_planner.lineup_case_supersession import (  # noqa: E402
    soft_supersede_lineup_case,
)
from app.services.commercial_planner.lineup_period_canonical import (  # noqa: E402
    active_lineup_case_filters,
)

CLONE_DB = os.environ.get("PO_CARRY_SMOKE_DB", "cip_po_carry_smoke")


def _db_name(url: str) -> str:
    path = urlparse(url.replace("+psycopg", "").replace("+asyncpg", "")).path
    return path.lstrip("/").split("?")[0]


def _admin_url() -> str:
    return os.environ.get(
        "SMOKE_ADMIN_URL",
        "postgresql+psycopg://postgres:Exarkun4252%21@127.0.0.1:5432/postgres",
    )


def _clone_url_from_env_file() -> str:
    env = (ROOT / ".env").read_text(encoding="utf-8")
    base = None
    for line in env.splitlines():
        if line.startswith("DATABASE_URL="):
            base = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if not base:
        raise SystemExit("DATABASE_URL missing from apps/api/.env")
    base = base.replace("+asyncpg", "+psycopg").replace("+psycopg2", "+psycopg")
    if not base.startswith("postgresql+psycopg://") and base.startswith("postgresql://"):
        base = base.replace("postgresql://", "postgresql+psycopg://", 1)
    prefix, _db = base.rsplit("/", 1)
    url = f"{prefix}/{CLONE_DB}"
    if _db_name(url) == "cip":
        raise SystemExit("STOP: clone URL resolves to cip")
    return url


def _ensure_clone(*, recreate: bool) -> str:
    clone_url = _clone_url_from_env_file()
    migrate_url = clone_url  # both overridden to same disposable DB
    print("DATABASE_URL_SYNC         ->", clone_url)
    print("DATABASE_URL_SYNC_MIGRATE ->", migrate_url)
    print("resolved_db_name          ->", _db_name(clone_url))

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
        if not exists:
            # TEMPLATE requires no other connections to cip
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
            print("clone_created", CLONE_DB)
        else:
            print("clone_reused", CLONE_DB)
    return clone_url


def _po_norms(db, case_id: int) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT po.po_number_norm
            FROM commercial_lineup_case_po cl
            JOIN purchase_order po ON po.id = cl.purchase_order_id
            WHERE cl.case_id = :cid
            ORDER BY 1
            """
        ),
        {"cid": case_id},
    ).scalars().all()
    return set(rows)


def _link_count(db, case_id: int) -> int:
    return int(
        db.execute(
            text("SELECT count(*) FROM commercial_lineup_case_po WHERE case_id = :cid"),
            {"cid": case_id},
        ).scalar()
        or 0
    )


def _mk_po(db, *, tok: str, suffix: str) -> PurchaseOrder:
    norm = f"CARRY{tok}{suffix}"
    po = PurchaseOrder(po_number_raw=norm, po_number_norm=norm)
    db.add(po)
    db.flush()
    return po


def _mk_case(db, *, tok: str, label: str, status: str = "draft_imported") -> CommercialLineupCase:
    case = CommercialLineupCase(
        file_name=f"carry_{label}_{tok}.xlsx",
        period_label="2099 Q1",
        business_unit="NB",
        commercial_status=status,
        import_intent="historical_lineup_backfill",
        source_context="po_carry_clone_proof",
    )
    db.add(case)
    db.flush()
    return case


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate-clone", action="store_true")
    args = parser.parse_args()

    # C1 — both URLs override to disposable DB (env for any nested Settings reads)
    clone_url = _ensure_clone(recreate=args.recreate_clone)
    os.environ["DATABASE_URL_SYNC"] = clone_url
    os.environ["DATABASE_URL_SYNC_MIGRATE"] = clone_url
    # Also override DATABASE_URL so Settings cannot silently fall back to cip
    async_url = clone_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    os.environ["DATABASE_URL"] = async_url

    engine = create_engine(clone_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        dbn = db.execute(text("SELECT current_database()")).scalar()
        print("C1 current_database()", dbn)
        if dbn != CLONE_DB:
            raise SystemExit(f"STOP: expected {CLONE_DB}, got {dbn}")

        tok = secrets.token_hex(3)

        # --- C2: loser with 3 POs, winner with 0 ---
        loser = _mk_case(db, tok=tok, label="loser_c2", status="po_issued")
        winner = _mk_case(db, tok=tok, label="winner_c2")
        pos = [_mk_po(db, tok=tok, suffix=s) for s in ("A", "B", "C")]
        for po in pos:
            db.add(
                CommercialLineupCasePo(
                    case_id=int(loser.id), purchase_order_id=int(po.id), notes="seed"
                )
            )
        db.flush()
        loser_before = _link_count(db, int(loser.id))
        result = soft_supersede_lineup_case(
            db, loser_case_id=int(loser.id), winner_case_id=int(winner.id)
        )
        db.commit()
        db.refresh(loser)
        db.refresh(winner)
        w_count = _link_count(db, int(winner.id))
        l_count = _link_count(db, int(loser.id))
        w_set = _po_norms(db, int(winner.id))
        l_set = _po_norms(db, int(loser.id))
        print(
            "C2",
            {
                "winner_link_count": w_count,
                "winner_po_set": sorted(w_set),
                "loser_link_count": l_count,
                "loser_link_count_unchanged": l_count == loser_before == 3,
                "loser_status": loser.commercial_status,
                "loser_superseded_by": loser.superseded_by_case_id,
                "carry": result["carry"],
            },
        )
        assert w_count == 3 and l_count == 3 and w_set == l_set
        assert loser.commercial_status == "superseded"
        assert int(loser.superseded_by_case_id) == int(winner.id)

        # --- C3: re-run same supersession ---
        result2 = soft_supersede_lineup_case(
            db, loser_case_id=int(loser.id), winner_case_id=int(winner.id)
        )
        db.commit()
        w_count2 = _link_count(db, int(winner.id))
        l_count2 = _link_count(db, int(loser.id))
        print(
            "C3 idempotent",
            {
                "winner_link_count": w_count2,
                "loser_link_count": l_count2,
                "carried": result2["carry"]["carried"],
                "skipped_existing": result2["carry"]["skipped_existing"],
                "already_superseded": result2["already_superseded"],
            },
        )
        assert w_count2 == 3 and l_count2 == 3
        assert result2["carry"]["carried"] == 0
        assert result2["carry"]["skipped_existing"] == 3

        # --- C4: winner already holds one of loser's POs ---
        tok4 = secrets.token_hex(3)
        loser4 = _mk_case(db, tok=tok4, label="loser_c4", status="po_issued")
        winner4 = _mk_case(db, tok=tok4, label="winner_c4")
        shared = _mk_po(db, tok=tok4, suffix="S")
        only_loser = _mk_po(db, tok=tok4, suffix="L")
        only_winner = _mk_po(db, tok=tok4, suffix="W")
        db.add(CommercialLineupCasePo(case_id=int(loser4.id), purchase_order_id=int(shared.id)))
        db.add(CommercialLineupCasePo(case_id=int(loser4.id), purchase_order_id=int(only_loser.id)))
        db.add(CommercialLineupCasePo(case_id=int(winner4.id), purchase_order_id=int(shared.id)))
        db.add(CommercialLineupCasePo(case_id=int(winner4.id), purchase_order_id=int(only_winner.id)))
        db.flush()
        soft_supersede_lineup_case(
            db, loser_case_id=int(loser4.id), winner_case_id=int(winner4.id)
        )
        db.commit()
        w4 = _po_norms(db, int(winner4.id))
        l4 = _po_norms(db, int(loser4.id))
        expected = {shared.po_number_norm, only_loser.po_number_norm, only_winner.po_number_norm}
        print(
            "C4 union",
            {
                "winner_po_set": sorted(w4),
                "loser_po_set": sorted(l4),
                "winner_count": _link_count(db, int(winner4.id)),
                "loser_count": _link_count(db, int(loser4.id)),
                "union_ok": w4 == expected,
            },
        )
        assert w4 == expected
        assert _link_count(db, int(winner4.id)) == 3
        assert _link_count(db, int(loser4.id)) == 2

        # --- C5: mid-tx failure → full rollback ---
        tok5 = secrets.token_hex(3)
        loser5 = _mk_case(db, tok=tok5, label="loser_c5", status="po_issued")
        winner5 = _mk_case(db, tok=tok5, label="winner_c5")
        po5 = [_mk_po(db, tok=tok5, suffix=s) for s in ("X", "Y")]
        for po in po5:
            db.add(CommercialLineupCasePo(case_id=int(loser5.id), purchase_order_id=int(po.id)))
        db.commit()
        l5_id, w5_id = int(loser5.id), int(winner5.id)
        try:
            with Session() as db2:
                assert db2.execute(text("SELECT current_database()")).scalar() == CLONE_DB
                soft_supersede_lineup_case(db2, loser_case_id=l5_id, winner_case_id=w5_id)
                # Force failure after status+carry flushed but before commit
                raise RuntimeError("forced_mid_carry_failure")
        except RuntimeError as exc:
            print("C5 caught", str(exc))
        with Session() as db3:
            assert db3.execute(text("SELECT current_database()")).scalar() == CLONE_DB
            loser5b = db3.get(CommercialLineupCase, l5_id)
            winner5b = db3.get(CommercialLineupCase, w5_id)
            print(
                "C5 rollback",
                {
                    "loser_status": loser5b.commercial_status,
                    "loser_superseded_by": loser5b.superseded_by_case_id,
                    "winner_links": _link_count(db3, w5_id),
                    "loser_links": _link_count(db3, l5_id),
                },
            )
            assert loser5b.commercial_status == "po_issued"
            assert loser5b.superseded_by_case_id is None
            assert _link_count(db3, w5_id) == 0
            assert _link_count(db3, l5_id) == 2

        # --- C6: active filters see winner, not loser ---
        from sqlalchemy import select

        active_ids = set(
            db.scalars(
                select(CommercialLineupCase.id).where(*active_lineup_case_filters())
            ).all()
        )
        # Re-query C2 cases
        loser_active = int(loser.id) in active_ids
        winner_active = int(winner.id) in active_ids
        # Active consumer join: case_po ∩ active cases
        active_po_case_ids = set(
            db.execute(
                text(
                    """
                    SELECT DISTINCT cl.case_id
                    FROM commercial_lineup_case_po cl
                    JOIN commercial_lineup_case c ON c.id = cl.case_id
                    WHERE c.superseded_by_case_id IS NULL
                      AND c.commercial_status NOT IN ('cancelled', 'superseded')
                      AND cl.case_id IN (:l, :w)
                    """
                ),
                {"l": int(loser.id), "w": int(winner.id)},
            ).scalars().all()
        )
        print(
            "C6 active_consumers",
            {
                "loser_in_active_filters": loser_active,
                "winner_in_active_filters": winner_active,
                "active_po_case_ids_for_pair": sorted(active_po_case_ids),
            },
        )
        assert not loser_active
        assert winner_active
        assert active_po_case_ids == {int(winner.id)}

    print("ALL_CLONE_SCENARIOS_PASS")


if __name__ == "__main__":
    main()
