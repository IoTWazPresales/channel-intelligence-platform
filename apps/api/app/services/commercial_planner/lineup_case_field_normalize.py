"""Align ``commercial_lineup_case`` BU / product_line fields for PO coverage matching."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase


def normalize_lineup_case_line_fields_sync(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    """Set ``product_line`` from ``business_unit`` when missing or mismatched; backfill null BU from PL."""
    rows = list(db.scalars(select(CommercialLineupCase)).all())
    updates: list[dict[str, Any]] = []

    for row in rows:
        bu = (row.business_unit or "").strip() or None
        pl = (row.product_line or "").strip() or None
        target_bu = bu
        target_pl = pl
        if bu:
            target_pl = bu
        elif pl:
            target_bu = pl
            target_pl = pl
        if target_bu == bu and target_pl == pl:
            continue
        if len(updates) < 20:
            updates.append(
                {
                    "case_id": int(row.id),
                    "before": {"business_unit": bu, "product_line": pl},
                    "after": {"business_unit": target_bu, "product_line": target_pl},
                }
            )
        if not dry_run:
            row.business_unit = target_bu
            row.product_line = target_pl

    if not dry_run and updates:
        db.commit()

    return {
        "dry_run": dry_run,
        "cases_scanned": len(rows),
        "cases_updated": 0 if dry_run else len(updates),
        "would_update": len(updates),
        "samples": updates,
    }
