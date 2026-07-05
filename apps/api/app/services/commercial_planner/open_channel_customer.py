"""Controlled Open Channel customer account for commercial planner sync (reference data).

This is not auto-creation from upload tokens. The OPEN_CHANNEL dim_customer row is **system
reference data** (global ``dim_customer``), ensured by:

- ``alembic upgrade head`` (migration ``20260429_0022``), and/or
- ``python scripts/seed.py --commercial-system-reference-only`` (repair, no DB wipe).

Demo ``seed_demo.run()`` also calls the same ensure helper after its wipe — not the only path.

Sync uses this row only when a lineup row is flagged as Open Channel staging.

If sync preview shows open_channel_account_missing, treat it as missing reference data, not a
per-upload row mapping defect.

Convenience (default ``pnpm local:db:seed`` / ``pnpm docker:seed`` runs **destructive** demo seed;
use ``--commercial-system-reference-only`` when you must not wipe).
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer

OPEN_CHANNEL_CUSTOMER_CODE = "OPEN_CHANNEL"
OPEN_CHANNEL_CUSTOMER_NAME = "Open Channel"


async def get_open_channel_customer_id(db: AsyncSession) -> int | None:
    """Return dim_customer.id for code OPEN_CHANNEL, or None if not provisioned."""
    r = await db.execute(select(DimCustomer.id).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
    return r.scalar_one_or_none()


async def get_open_channel_canonical_and_aliases(
    db: AsyncSession,
) -> tuple[int | None, frozenset[int]]:
    """Canonical OPEN_CHANNEL id plus steward-created duplicates with the same display name.

    Shipment evidence often resolves to a provisional TMP-CUST row named "Open Channel" while
    lineup staging attributes plan qty to the controlled OPEN_CHANNEL reference row.
    """
    canonical = await get_open_channel_customer_id(db)
    alias_ids: set[int] = set()
    if canonical is not None:
        alias_ids.add(int(canonical))
    rows = (
        await db.execute(
            select(DimCustomer.id).where(
                func.lower(func.trim(DimCustomer.name)) == OPEN_CHANNEL_CUSTOMER_NAME.lower(),
                DimCustomer.code != OPEN_CHANNEL_CUSTOMER_CODE,
            )
        )
    ).scalars().all()
    for cid in rows:
        if cid is not None:
            alias_ids.add(int(cid))
    return canonical, frozenset(alias_ids)


def canonical_open_channel_customer_id(
    customer_id: int | None,
    *,
    canonical_id: int | None,
    alias_ids: frozenset[int],
) -> int | None:
    """Map provisional Open Channel dim rows onto the controlled OPEN_CHANNEL account."""
    if customer_id is None:
        return None
    cid = int(customer_id)
    if canonical_id is not None and cid in alias_ids:
        return int(canonical_id)
    return cid
