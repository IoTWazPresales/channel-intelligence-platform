"""Controlled placeholder distributor for commercial planner sync (reference data).

CommercialPlanLine.distributor_id is NOT NULL. When a lineup row has no distributor mapped
and no distributor_token to resolve, sync uses this dim row instead of inventing distributors
from uploads.

Provision idempotently as **system reference** (same as ``OPEN_CHANNEL``):

- ``alembic upgrade head`` (migration ``20260429_0022``), and/or
- ``python scripts/seed.py --commercial-system-reference-only``.

Demo seed also ensures these rows after its DB wipe — not the portability path for non-demo DBs.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimDistributor

UNASSIGNED_DISTRIBUTOR_CODE = "UNASSIGNED"
UNASSIGNED_DISTRIBUTOR_NAME = "Unassigned Distributor"


async def get_unassigned_distributor_id(db: AsyncSession) -> int | None:
    """Return dim_distributor.id for code UNASSIGNED, or None if not provisioned."""
    r = await db.execute(select(DimDistributor.id).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE))
    return r.scalar_one_or_none()
