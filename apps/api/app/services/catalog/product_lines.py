"""Sellable product-line (BU) vocabulary — the one source (D-g, N-0040).

Operator decision D-g: the sellable BU grain is every ``dim_product.product_line`` value as it
appears in the catalogue. No code path may carry its own list of line codes; sheet/folder BU
inference, archive path parsing, filename fallbacks and pickers all read this set.

``product_line`` NULL / blank rows are excluded from the set and counted separately so the
count can be surfaced as a data-quality finding. Display labels are presentation only and
never decide membership.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimProduct

# Short TTL: PM commits may run in a worker process, where the in-process invalidate hook
# cannot reach the API process.
_CACHE_TTL_SECONDS = 60.0

_lock = threading.Lock()
_cache_entry: tuple["SellableProductLines", float] | None = None


@dataclass(frozen=True, slots=True)
class ProductLineEntry:
    code: str
    product_count: int
    label: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "product_count": self.product_count, "label": self.label}


@dataclass(frozen=True, slots=True)
class SellableProductLines:
    lines: tuple[ProductLineEntry, ...]
    null_product_line_count: int

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(line.code for line in self.lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "product_lines": [line.to_dict() for line in self.lines],
            "null_product_line_count": self.null_product_line_count,
        }


def invalidate_sellable_product_lines_cache() -> None:
    """Drop the cached set (after Product Master commit, and in tests)."""
    global _cache_entry
    with _lock:
        _cache_entry = None


async def list_sellable_product_lines(
    db: AsyncSession, *, force_refresh: bool = False
) -> SellableProductLines:
    """Distinct trimmed non-blank ``dim_product.product_line`` values, most products first."""
    global _cache_entry
    now = time.monotonic()
    if not force_refresh:
        with _lock:
            entry = _cache_entry
        if entry is not None and now - entry[1] < _CACHE_TTL_SECONDS:
            return entry[0]

    code = func.trim(DimProduct.product_line)
    rows = (
        await db.execute(
            select(code.label("code"), func.count(DimProduct.id).label("n"))
            .where(DimProduct.product_line.isnot(None), code != "")
            .group_by(code)
            .order_by(func.count(DimProduct.id).desc(), code)
        )
    ).all()
    null_count = (
        await db.execute(
            select(func.count(DimProduct.id)).where(
                (DimProduct.product_line.is_(None)) | (func.trim(DimProduct.product_line) == "")
            )
        )
    ).scalar_one()
    result = SellableProductLines(
        lines=tuple(ProductLineEntry(code=str(c), product_count=int(n), label=str(c)) for c, n in rows),
        null_product_line_count=int(null_count or 0),
    )
    with _lock:
        _cache_entry = (result, now)
    return result


async def sellable_line_codes(db: AsyncSession) -> frozenset[str]:
    """Membership set for sheet / folder / filename BU inference."""
    return (await list_sellable_product_lines(db)).codes
