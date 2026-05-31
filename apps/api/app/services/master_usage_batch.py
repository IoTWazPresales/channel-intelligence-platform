"""Batched reference-count utilities for master-entity delete checks.

Reference checks compile to exactly ONE ``UNION ALL`` statement per call to
``batch_counts_multi_table`` — building subqueries in Python is compile-time only;
there is no per-table ``await db.execute`` loop.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, ColumnElement, Select, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession


def count_subquery_for_columns(
    label: str,
    columns: list[ColumnElement[Any]],
    entity_ids: list[int],
) -> Select:
    """Build a SELECT (lbl, entity_id, cnt) subquery for one reference check."""
    ids = [int(i) for i in entity_ids if isinstance(i, int) and i > 0]
    cnt_expr = cast(func.count(), BigInteger).label("cnt")
    if len(columns) == 1:
        col = columns[0]
        return (
            select(
                literal(label, type_=None).label("lbl"),
                col.label("entity_id"),
                cnt_expr,
            )
            .where(col.in_(ids))
            .group_by(col)
        )
    inner = union_all(*[
        select(col.label("entity_id")).where(col.in_(ids)) for col in columns
    ]).subquery()
    return select(
        literal(label, type_=None).label("lbl"),
        inner.c.entity_id.label("entity_id"),
        cnt_expr,
    ).group_by(inner.c.entity_id)


async def batch_counts_multi_table(
    db: AsyncSession,
    subqueries: list[Select],
    entity_ids: list[int],
) -> dict[int, list[dict[str, int | str]]]:
    """Execute all reference-count checks as a single UNION ALL statement.

    Exactly one ``await db.execute`` — one database round trip.
    """
    ids = [int(i) for i in entity_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids or not subqueries:
        return out
    combined = union_all(*subqueries)
    rows = (await db.execute(combined)).all()
    for row in rows:
        mapping = row._mapping
        entity_id = mapping.get("entity_id")
        if entity_id is None:
            continue
        eid = int(entity_id)
        cnt = int(mapping.get("cnt") or 0)
        if eid in out and cnt > 0:
            out[eid].append({"label": str(mapping.get("lbl")), "count": cnt})
    return out


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
