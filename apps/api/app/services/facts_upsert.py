"""Shared helpers for creating dimension rows while importing fact tables."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimProduct


async def get_or_create_product(db: AsyncSession, sku: str) -> DimProduct:
    sku = sku.strip()
    if not sku:
        raise ValueError("sku is required")
    res = await db.execute(select(DimProduct).where(DimProduct.sku == sku))
    row = res.scalar_one_or_none()
    if row:
        return row
    row = DimProduct(sku=sku, name=f"Imported — {sku}")
    db.add(row)
    await db.flush()
    return row


async def get_or_create_customer(db: AsyncSession, code: str) -> DimCustomer:
    code = code.strip()
    if not code:
        raise ValueError("customer_code is required")
    res = await db.execute(select(DimCustomer).where(DimCustomer.code == code))
    row = res.scalar_one_or_none()
    if row:
        from app.services.merge_redirect import (
            follow_customer_merge_redirect_async,
            is_merged_customer_row,
        )

        if is_merged_customer_row(row):
            winner_id = await follow_customer_merge_redirect_async(db, int(row.id))
            if winner_id is not None and int(winner_id) != int(row.id):
                winner = await db.get(DimCustomer, int(winner_id))
                if winner is not None:
                    return winner
        return row
    row = DimCustomer(code=code, name=f"Imported — {code}")
    db.add(row)
    await db.flush()
    return row


async def resolve_channel_id(db: AsyncSession, code: str | None) -> int | None:
    if code is None or not str(code).strip():
        return None
    code = str(code).strip()
    res = await db.execute(select(DimChannel).where(DimChannel.code == code))
    ch = res.scalar_one_or_none()
    if not ch:
        raise ValueError(f"Unknown channel_code {code!r}")
    return ch.id


async def resolve_customer_id(db: AsyncSession, code: str | None, *, create: bool) -> int | None:
    if code is None or not str(code).strip():
        return None
    if create:
        return (await get_or_create_customer(db, code)).id
    res = await db.execute(select(DimCustomer).where(DimCustomer.code == str(code).strip()))
    row = res.scalar_one_or_none()
    if not row:
        raise ValueError(f"Unknown customer_code {str(code).strip()!r}")
    from app.services.merge_redirect import follow_customer_merge_redirect_async

    return await follow_customer_merge_redirect_async(db, int(row.id))
