"""Queue a price entry when the SKU is not already a product. Never creates dim_product."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimProduct
from app.models.pricing_unknown_sku import PricingUnknownSku

UNKNOWN_PRICING_SKU_MESSAGE = (
    "This SKU is not in the product master. It is on the product catalogue gaps queue. No product was created."
)
UNKNOWN_PRICING_SKU_HREF = "/admin/product-master-gaps"


async def find_product_by_sku(db: AsyncSession, sku: str) -> DimProduct | None:
    cleaned = sku.strip()
    if not cleaned:
        raise ValueError("sku is required")
    res = await db.execute(select(DimProduct).where(DimProduct.sku == cleaned))
    return res.scalar_one_or_none()


async def queue_unknown_pricing_sku(
    db: AsyncSession,
    *,
    sku: str,
    list_price: float,
    net_price: float,
    currency: str,
    effective_date: date,
    customer_code: str | None,
    channel_code: str | None,
) -> str:
    cleaned = sku.strip()
    money = (currency or "USD").strip() or "USD"
    customer = (customer_code or "").strip() or None
    channel = (channel_code or "").strip() or None
    stmt = insert(PricingUnknownSku).values(
        sku=cleaned,
        list_price=list_price,
        net_price=net_price,
        currency=money,
        effective_date=effective_date,
        customer_code=customer,
        channel_code=channel,
        attempt_count=1,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[PricingUnknownSku.sku],
        set_={
            "list_price": list_price,
            "net_price": net_price,
            "currency": money,
            "effective_date": effective_date,
            "customer_code": customer,
            "channel_code": channel,
            "attempt_count": PricingUnknownSku.attempt_count + 1,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    return cleaned


async def clear_queued_pricing_sku(db: AsyncSession, sku: str) -> None:
    await db.execute(delete(PricingUnknownSku).where(PricingUnknownSku.sku == sku.strip()))
