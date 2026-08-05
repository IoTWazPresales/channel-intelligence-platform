#!/usr/bin/env python3
"""Prove FLAG≠BLOCK for contested competition annotation on disposable clone.

C6: contested status must not prevent link_case_to_existing_po.
Uses cip_po_carry_smoke (or PO_COMP_SMOKE_DB). Never targets cip.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo  # noqa: E402
from app.models.purchase_order import PurchaseOrder  # noqa: E402
from app.services.commercial_planner.lineup_case_po_confirm import (  # noqa: E402
    insert_case_po_link_if_missing,
)
from app.services.commercial_planner.lineup_case_status import (  # noqa: E402
    commercial_status_after_po_link,
)
from app.services.commercial_planner.lineup_po_competition import (  # noqa: E402
    annotate_proposals_with_competition,
    classify_proposals_competition,
)

CLONE_DB = os.environ.get("PO_COMP_SMOKE_DB", "cip_po_carry_smoke")


def _db_name(url: str) -> str:
    path = urlparse(url.replace("+psycopg", "").replace("+asyncpg", "")).path
    return path.lstrip("/").split("?")[0]


def _clone_url() -> str:
    env = (ROOT / ".env").read_text(encoding="utf-8")
    base = None
    for line in env.splitlines():
        if line.startswith("DATABASE_URL="):
            base = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if not base:
        raise SystemExit("DATABASE_URL missing")
    base = base.replace("+asyncpg", "+psycopg").replace("+psycopg2", "+psycopg")
    if base.startswith("postgresql://"):
        base = base.replace("postgresql://", "postgresql+psycopg://", 1)
    prefix, _ = base.rsplit("/", 1)
    url = f"{prefix}/{CLONE_DB}"
    if _db_name(url) == "cip":
        raise SystemExit("STOP: clone URL resolves to cip")
    return url


def main() -> None:
    sync = _clone_url()
    migrate = sync
    print("DATABASE_URL_SYNC ->", sync)
    print("DATABASE_URL_SYNC_MIGRATE ->", migrate)
    os.environ["DATABASE_URL_SYNC"] = sync
    os.environ["DATABASE_URL_SYNC_MIGRATE"] = migrate
    os.environ["DATABASE_URL"] = sync.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

    engine = create_engine(sync, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        dbn = db.execute(text("SELECT current_database()")).scalar()
        print("C1 current_database()", dbn)
        if dbn != CLONE_DB:
            raise SystemExit(f"STOP: expected {CLONE_DB}, got {dbn}")

        tok = secrets.token_hex(3)
        # Contested pair: same BU same period — annotate then still link (FLAG≠BLOCK)
        c1 = CommercialLineupCase(
            file_name=f"comp_a_{tok}.xlsx",
            period_label="2099 Q2",
            business_unit="NB",
            commercial_status="draft_imported",
            import_intent="historical_lineup_backfill",
            source_context="po_comp_clone",
        )
        c2 = CommercialLineupCase(
            file_name=f"comp_b_{tok}.xlsx",
            period_label="2099 Q2",
            business_unit="NB",
            commercial_status="draft_imported",
            import_intent="historical_lineup_backfill",
            source_context="po_comp_clone",
        )
        db.add_all([c1, c2])
        db.flush()
        po = PurchaseOrder(po_number_raw=f"COMP{tok}", po_number_norm=f"COMP{tok}")
        db.add(po)
        db.flush()

        props = [
            {"case_id": int(c1.id), "po_number_norm": po.po_number_norm},
            {"case_id": int(c2.id), "po_number_norm": po.po_number_norm},
        ]
        from datetime import date

        classifications = classify_proposals_competition(
            props,
            case_meta={
                int(c1.id): {
                    "bu": "NB",
                    "inferred_period_start": date(2099, 4, 1),
                    "period_label": "2099 Q2",
                },
                int(c2.id): {
                    "bu": "NB",
                    "inferred_period_start": date(2099, 4, 1),
                    "period_label": "2099 Q2",
                },
            },
            case_product_ids={int(c1.id): {1}, int(c2.id): {1}},
            ship_products_by_po_norm={po.po_number_norm: {1: "NB"}},
        )
        annotate_proposals_with_competition(props, classifications)
        assert props[0]["competition"]["status"] == "contested"
        assert props[0]["competition"]["blocks_apply"] is False

        # Apply path ignores competition — insert link anyway
        inserted = insert_case_po_link_if_missing(
            db, case_id=int(c1.id), purchase_order_id=int(po.id), notes="c6_flag_not_block"
        )
        c1.commercial_status = commercial_status_after_po_link(c1.commercial_status)
        db.flush()
        count = db.execute(
            text("SELECT count(*) FROM commercial_lineup_case_po WHERE case_id=:c"),
            {"c": int(c1.id)},
        ).scalar()
        print(
            "C6 FLAG_NEQ_BLOCK",
            {
                "competition_status": props[0]["competition"]["status"],
                "blocks_apply": props[0]["competition"]["blocks_apply"],
                "link_inserted": inserted,
                "link_count": int(count),
            },
        )
        assert inserted and int(count) == 1
        db.rollback()  # leave no residue
    print("C6_PASS")


if __name__ == "__main__":
    main()
