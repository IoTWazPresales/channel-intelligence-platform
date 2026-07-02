"""Normalize ``commercial_lineup_case.period_label`` display values on ``cip``."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.lineup_period_canonical import display_period_label_from_period_start


def normalize_lineup_case_period_labels_sync(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(CommercialLineupCase).where(CommercialLineupCase.inferred_period_start.isnot(None))
        ).all()
    )
    before_formats: dict[str, int] = {}
    after_formats: dict[str, int] = {}
    updates = 0
    samples: list[dict[str, Any]] = []

    for row in rows:
        label = (row.period_label or "").strip() or "(null)"
        before_formats[label] = before_formats.get(label, 0) + 1
        target = display_period_label_from_period_start(row.inferred_period_start)  # type: ignore[arg-type]
        after_formats[target] = after_formats.get(target, 0) + 1
        if (row.period_label or "").strip() != target:
            if len(samples) < 15:
                samples.append(
                    {
                        "case_id": int(row.id),
                        "before": row.period_label,
                        "after": target,
                        "inferred_period_start": row.inferred_period_start.isoformat(),
                    }
                )
            if not dry_run:
                row.period_label = target
            updates += 1

    if not dry_run and updates:
        db.commit()

    return {
        "dry_run": dry_run,
        "cases_with_period_start": len(rows),
        "labels_updated": 0 if dry_run else updates,
        "would_update": updates,
        "before_label_counts": before_formats,
        "after_label_counts": after_formats,
        "samples": samples,
    }
