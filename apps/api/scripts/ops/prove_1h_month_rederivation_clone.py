#!/usr/bin/env python3
"""Prove month-derived 1H re-derivation on a disposable clone (destructive-class)."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.services.commercial_planner.current_lineup_seed import ensure_lineup_import_seed_sync
from app.services.commercial_planner.lineup_bulk_backfill_preview import BULK_SOURCE_CODE, BULK_TEMPLATE_SLUG
from app.services.commercial_planner.lineup_bulk_rederivation import (
    REDERIVATION_PREVIEW_KEY,
    apply_1h_rederivation_sync,
    build_1h_rederivation_collisions,
    build_1h_rederivation_preview,
)


def _db_name(url: str) -> str:
    path = urlparse(url.replace("+psycopg", "")).path
    return path.lstrip("/").split("?")[0]


async def _run_preview(async_url: str) -> dict:
    engine = create_async_engine(async_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        return await build_1h_rederivation_preview(db)


def main() -> None:
    sync_url = os.environ.get("DATABASE_URL_SYNC", "")
    migrate_url = os.environ.get("DATABASE_URL_SYNC_MIGRATE", sync_url)
    print("DATABASE_URL_SYNC ->", _db_name(sync_url))
    print("DATABASE_URL_SYNC_MIGRATE ->", _db_name(migrate_url))
    if _db_name(sync_url) == "cip" or _db_name(migrate_url) == "cip":
        raise SystemExit("STOP: clone URL must not target cip")

    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgresql+psycopg://", "postgresql+asyncpg://"
    )
    preview = asyncio.run(_run_preview(async_url))
    proposals = preview.get("rederivation_proposals") or []
    case35 = next((p for p in proposals if p.get("source_case_id") == 35), None)
    if not case35:
        raise SystemExit("GATE FAIL: case 35 not in preview")

    ev = next(
        (
            row
            for row in case35.get("line_allocations") or []
            if row.get("customer_token") == "Evetech" and "UX3405CA" in str(row.get("model_raw") or "")
        ),
        None,
    )
    print("Evetech preview:", json.dumps(ev, indent=2))
    if not ev or float(ev.get("q1_allocated_units") or 0) != 36.0:
        raise SystemExit(f"GATE FAIL: Evetech Q1 expected 36, got {ev}")

    engine = create_engine(sync_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        po_before = int(db.scalar(text("select count(*) from commercial_lineup_case_po where case_id=35")) or 0)
        ensure_lineup_import_seed_sync(
            db.connection(), template_slug=BULK_TEMPLATE_SLUG, source_code=BULK_SOURCE_CODE
        )
        db.commit()
        source = db.execute(
            select(SourceDefinition)
            .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
            .where(ImportTemplate.slug == BULK_TEMPLATE_SLUG, SourceDefinition.code == BULK_SOURCE_CODE)
            .limit(1)
        ).scalar_one()
        job = ImportJob(
            source_id=source.id,
            template_slug=BULK_TEMPLATE_SLUG,
            import_mode="preview",
            status="validated",
            stage="validated",
            file_name="lineup_1h_month_rederivation_clone_proof",
            staged_metadata={"bulk_lineup_backfill_preview": {REDERIVATION_PREVIEW_KEY: preview}},
        )
        db.add(job)
        db.commit()

        confirmations: dict[str, str] = {}
        for g in build_1h_rederivation_collisions(proposals):
            existing = [m for m in g.get("members") or [] if m.get("kind") == "existing_case"]
            if existing:
                confirmations[g["supersession_group_key"]] = str(existing[0]["member_key"])

        result = apply_1h_rederivation_sync(
            int(job.id),
            approved_proposal_keys=[str(case35["proposal_key"])],
            supersession_confirmations=confirmations,
        )
        print("apply:", json.dumps(result, indent=2, default=str))
        db.expire_all()

        ev_line = db.execute(
            text(
                """
                select l.quantity_units, l.diagnostic_codes::text as diag
                from commercial_lineup_line l
                where l.case_id=35 and l.customer_token='Evetech'
                  and l.model_raw like '%UX3405CA-OU93210BL0X%'
                limit 1
                """
            )
        ).mappings().first()
        qty = float(ev_line["quantity_units"]) if ev_line else -1
        print("Evetech after:", dict(ev_line or {}))
        if qty != 36.0:
            raise SystemExit(f"GATE FAIL: Evetech quantity_units={qty}, expected 36")

        planned = db.scalar(
            text(
                """
                select coalesce(sum(l.quantity_units), 0)
                from commercial_lineup_line l
                where l.case_id=35 and l.customer_token='Evetech'
                  and l.model_raw like '%UX3405CA-OU93210BL0X%'
                """
            )
        )
        print("Evetech PO reconciliation planned (line sum):", planned)
        if float(planned or 0) != 36.0:
            raise SystemExit(f"GATE FAIL: Evetech planned={planned}, expected 36")

        po_after = int(db.scalar(text("select count(*) from commercial_lineup_case_po where case_id=35")) or 0)
        if po_after != po_before:
            raise SystemExit(f"GATE FAIL: PO links {po_before} -> {po_after}")

        q2_outcome = next((r for r in result.get("results") or [] if r.get("source_case_id") == 35), {})
        if q2_outcome.get("q2_outcome") != "skipped_collision_existing_winner":
            raise SystemExit(f"GATE FAIL: q2_outcome={q2_outcome.get('q2_outcome')}")

        no_month = db.execute(
            text(
                """
                select count(*) from commercial_lineup_line l
                join commercial_lineup_case c on c.id=l.case_id
                where c.id=16 and l.diagnostic_codes::text like '%uniform_half%'
                """
            )
        ).scalar()
        print("case16 uniform_half lines (no month block):", no_month)

    print("CLONE PROOF GREEN")


if __name__ == "__main__":
    main()
