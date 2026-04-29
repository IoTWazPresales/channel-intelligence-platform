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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer

OPEN_CHANNEL_CUSTOMER_CODE = "OPEN_CHANNEL"
OPEN_CHANNEL_CUSTOMER_NAME = "Open Channel"


async def get_open_channel_customer_id(db: AsyncSession) -> int | None:
    """Return dim_customer.id for code OPEN_CHANNEL, or None if not provisioned."""
    r = await db.execute(select(DimCustomer.id).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))
    return r.scalar_one_or_none()
