"""Batched GROUP BY counts for master-entity delete reference checks."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def batch_counts_for_column(
    db: AsyncSession,
    column: ColumnElement[Any],
    entity_ids: list[int],
) -> dict[int, int]:
    """Return {entity_id: row_count} for rows where ``column`` matches one of ``entity_ids``."""
    ids = [int(i) for i in entity_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    stmt = select(column, func.count()).where(column.in_(ids)).group_by(column)
    rows = (await db.execute(stmt)).all()
    return {int(k): int(v) for k, v in rows if k is not None}


def merge_batch_refs(
    out: dict[int, list[dict[str, int | str]]],
    entity_ids: list[int],
    label: str,
    counts: dict[int, int],
) -> None:
    for eid in entity_ids:
        n = counts.get(eid, 0)
        if n > 0:
            out[eid].append({"label": label, "count": n})
