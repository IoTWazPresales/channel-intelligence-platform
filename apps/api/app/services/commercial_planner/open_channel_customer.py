"""Controlled Open Channel customer account for commercial planner sync (reference data).

This is not auto-creation from upload tokens. The OPEN_CHANNEL dim_customer row should exist
after seed (see seed_demo). Sync uses it only when a lineup row is flagged as Open Channel staging.
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
