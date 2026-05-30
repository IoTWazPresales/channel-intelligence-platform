"""Batched reference-count utilities for master-entity delete checks.

All reference checks for a given entity set are executed as a single UNION ALL
query — one network round trip regardless of how many tables are checked.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Select, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession


def count_subquery_for_columns(
    label: str,
    columns: list[ColumnElement[Any]],
    entity_ids: list[int],
) -> Select:
    """Build a SELECT (lbl, entity_id, cnt) subquery for one reference check.

    For single-column tables the subquery is a plain GROUP BY.
    For multi-column tables (e.g. product_id + replacement_candidate_id on the
    same table), the column references are merged via an inner UNION ALL so the
    caller receives a single aggregated count per entity — not one entry per
    column.
    """
    ids = [int(i) for i in entity_ids if isinstance(i, int) and i > 0]
    if len(columns) == 1:
        col = columns[0]
        return (
            select(literal(label).label("lbl"), col.label("entity_id"), func.count().label("cnt"))
            .where(col.in_(ids))
            .group_by(col)
        )
    inner = union_all(*[
        select(col.label("entity_id")).where(col.in_(ids)) for col in columns
    ]).subquery()
    return select(
        literal(label).label("lbl"),
        inner.c.entity_id.label("entity_id"),
        func.count().label("cnt"),
    ).group_by(inner.c.entity_id)


async def batch_counts_multi_table(
    db: AsyncSession,
    subqueries: list[Select],
    entity_ids: list[int],
) -> dict[int, list[dict[str, int | str]]]:
    """Execute all reference-count checks as a single UNION ALL query.

    ``subqueries`` should be built with ``count_subquery_for_columns`` or a
    hand-crafted SELECT that projects (lbl text, entity_id int, cnt bigint).

    Returns ``{entity_id: [{label, count}, ...]}`` for every id in
    ``entity_ids``; ids with no references receive an empty list.
    """
    ids = [int(i) for i in entity_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids or not subqueries:
        return out
    combined = union_all(*subqueries)
    rows = (await db.execute(combined)).all()
    for lbl, entity_id, cnt in rows:
        if entity_id is None:
            continue
        eid = int(entity_id)
        if eid in out and int(cnt) > 0:
            out[eid].append({"label": str(lbl), "count": int(cnt)})
    return out


# ---------------------------------------------------------------------------
# Legacy helpers retained for backward compat (still used by callers that have
# not yet been migrated to batch_counts_multi_table).
# ---------------------------------------------------------------------------

async def batch_counts_for_column(
    db: AsyncSession,
    column: ColumnElement[Any],
    entity_ids: list[int],
) -> dict[int, int]:
    """Return {entity_id: row_count} for rows where ``column`` IN entity_ids."""
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
