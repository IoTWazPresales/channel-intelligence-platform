"""Display names on query results (Warren 2026-10-20: people read customer and product names, not ids).

Every row or series point that carries ``customer_id``, ``distributor_id`` or ``product_id`` gets
``customer_name``, ``distributor_name`` and ``product_name`` beside it (sales model or product name,
SKU when neither is set). Ids stay on the row for filtering and drill-down; screens show the names.
A name that is already on the row is kept.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct

logger = logging.getLogger(__name__)

_ID_FIELDS = (
    ("customer_id", "customer_name"),
    ("distributor_id", "distributor_name"),
    ("product_id", "product_name"),
)


def _ids(rows: list[dict[str, Any]], key: str) -> set[int]:
    out: set[int] = set()
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        try:
            out.add(int(v))
        except (TypeError, ValueError):
            continue
    return out


async def name_lookup(db: AsyncSession, rows: list[dict[str, Any]]) -> dict[str, dict[int, str]]:
    names: dict[str, dict[int, str]] = {"customer_id": {}, "distributor_id": {}, "product_id": {}}
    cids = _ids(rows, "customer_id")
    if cids:
        for r in (await db.execute(select(DimCustomer.id, DimCustomer.name).where(DimCustomer.id.in_(cids)))).all():
            names["customer_id"][int(r.id)] = r.name
    dids = _ids(rows, "distributor_id")
    if dids:
        for r in (await db.execute(select(DimDistributor.id, DimDistributor.name).where(DimDistributor.id.in_(dids)))).all():
            names["distributor_id"][int(r.id)] = r.name
    pids = _ids(rows, "product_id")
    if pids:
        stmt = select(DimProduct.id, DimProduct.sales_model_name, DimProduct.name, DimProduct.sku).where(DimProduct.id.in_(pids))
        for r in (await db.execute(stmt)).all():
            names["product_id"][int(r.id)] = r.sales_model_name or r.name or r.sku
    return names


async def attach_names(db: AsyncSession, *lists: list[dict[str, Any]] | None) -> None:
    """Add display names in place to every row of every list given."""
    rows = [r for lst in lists if lst for r in lst if isinstance(r, dict)]
    if not rows:
        return
    try:
        names = await name_lookup(db, rows)
    except Exception:  # noqa: BLE001 - names are presentation; a lookup failure never fails the query
        logger.warning("query result names could not be looked up", exc_info=True)
        return
    for r in rows:
        for id_key, name_key in _ID_FIELDS:
            if r.get(id_key) is None or r.get(name_key):
                continue
            try:
                n = names[id_key].get(int(r[id_key]))
            except (TypeError, ValueError):
                n = None
            if n:
                r[name_key] = n
