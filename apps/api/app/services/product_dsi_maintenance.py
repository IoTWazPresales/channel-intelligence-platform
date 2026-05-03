"""Admin maintenance: Distributor Sales & Inventory (DSI) facts for one product.

These rows are created by the DSI import pipeline; clearing them does not run Product Master
and does not delete ``dim_product``. Used only from explicit, confirm-gated HTTP endpoints.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInventoryDistributor, FactSalesSellout

# Must match DELETE body validation in ``products`` router.
CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT = "CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT"


async def dsi_fact_counts(db: AsyncSession, product_id: int) -> tuple[int, int]:
    inv_n = int(
        (
            await db.execute(
                select(func.count()).select_from(FactInventoryDistributor).where(
                    FactInventoryDistributor.product_id == product_id
                )
            )
        ).scalar_one()
    )
    sell_n = int(
        (
            await db.execute(
                select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.product_id == product_id)
            )
        ).scalar_one()
    )
    return inv_n, sell_n


async def dsi_dependency_detail_payload(db: AsyncSession, product_id: int) -> dict:
    row = await db.get(DimProduct, product_id)
    if not row:
        return {"error": "product_not_found", "product_id": product_id}
    inv_n, sell_n = await dsi_fact_counts(db, product_id)

    inv_samples: list[dict] = []
    if inv_n:
        inv_stmt = (
            select(
                FactInventoryDistributor.id,
                FactInventoryDistributor.as_of_date,
                FactInventoryDistributor.distributor_id,
                DimDistributor.code.label("distributor_code"),
                FactInventoryDistributor.source_import_job_id,
            )
            .join(DimDistributor, DimDistributor.id == FactInventoryDistributor.distributor_id)
            .where(FactInventoryDistributor.product_id == product_id)
            .order_by(FactInventoryDistributor.id)
            .limit(5)
        )
        for r in (await db.execute(inv_stmt)).all():
            inv_samples.append(
                {
                    "id": r.id,
                    "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
                    "distributor_id": r.distributor_id,
                    "distributor_code": r.distributor_code,
                    "source_import_job_id": r.source_import_job_id,
                }
            )

    sell_samples: list[dict] = []
    if sell_n:
        sell_stmt = (
            select(
                FactSalesSellout.id,
                FactSalesSellout.period_start,
                FactSalesSellout.customer_id,
                DimCustomer.code.label("customer_code"),
                FactSalesSellout.distributor_id,
                DimDistributor.code.label("distributor_code"),
                FactSalesSellout.source_import_job_id,
            )
            .join(DimCustomer, DimCustomer.id == FactSalesSellout.customer_id)
            .outerjoin(DimDistributor, DimDistributor.id == FactSalesSellout.distributor_id)
            .where(FactSalesSellout.product_id == product_id)
            .order_by(FactSalesSellout.id)
            .limit(5)
        )
        for r in (await db.execute(sell_stmt)).all():
            sell_samples.append(
                {
                    "id": r.id,
                    "period_start": r.period_start.isoformat() if r.period_start else None,
                    "customer_id": r.customer_id,
                    "customer_code": r.customer_code,
                    "distributor_id": r.distributor_id,
                    "distributor_code": r.distributor_code,
                    "source_import_job_id": r.source_import_job_id,
                }
            )

    total = inv_n + sell_n
    return {
        "product_id": product_id,
        "sku": row.sku,
        "maintenance_label": "Admin maintenance — Distributor sales & inventory facts",
        "confirm_token": CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT,
        "dependency_type": "distributor_sales_inventory",
        "blocks_product_delete": total > 0,
        "counts": {
            "fact_inventory_distributor": inv_n,
            "fact_sales_sellout": sell_n,
            "total_dsi_rows": total,
        },
        "distributor_inventory": {
            "kind": "distributor_inventory",
            "label": "Distributor inventory",
            "count": inv_n,
            "sample_rows": inv_samples,
            "clear_available": inv_n > 0,
        },
        "sell_out": {
            "kind": "sell_out",
            "label": "Sell-out",
            "count": sell_n,
            "sample_rows": sell_samples,
            "clear_available": sell_n > 0,
        },
    }


async def clear_dsi_facts_for_product(db: AsyncSession, product_id: int) -> dict[str, int]:
    """Delete DSI sell-out + distributor inventory facts for ``product_id`` only.

    Caller must ``commit`` (or roll back) the session.
    """
    inv_res = await db.execute(
        delete(FactInventoryDistributor).where(FactInventoryDistributor.product_id == product_id)
    )
    sell_res = await db.execute(delete(FactSalesSellout).where(FactSalesSellout.product_id == product_id))
    inv_deleted = int(getattr(inv_res, "rowcount", 0) or 0)
    sell_deleted = int(getattr(sell_res, "rowcount", 0) or 0)
    return {
        "fact_inventory_distributor_deleted": inv_deleted,
        "fact_sales_sellout_deleted": sell_deleted,
    }
