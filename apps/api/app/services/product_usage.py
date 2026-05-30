"""Product delete: hard blockers vs derived rows that are auto-cleaned."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_planner import CommercialSkuAssumption
from app.models.derived import (
    BuyRecommendation,
    CompetitivePositioning,
    ExceptionInboxItem,
    ForecastSummary,
    PricingRecommendation,
    PromoReadiness,
    StockHealth,
    StockRisk,
    WeeksOfStock,
)
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.fact_dsi_forecast import FactDsiForecast
from app.models.facts import (
    FactActivation,
    FactBuyPlan,
    FactCompetitorMapping,
    FactForecast,
    FactInboundShipment,
    FactInventoryCustomer,
    FactInventoryDistributor,
    FactPricing,
    FactProductRoadmap,
    FactPromotionPerformance,
    FactPromotionPlan,
    FactSalesSellin,
    FactSalesSellout,
    FactSupport,
    FactBudgetRequest,
)
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import ImportDistributorSiStagingLine, ImportEntityMappingCandidate
from app.models.lineup import FactLineupPlanItem
from app.models.mapping import ProductAlias
from app.models.product_catalog import CatalogProduct
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.master_usage_batch import batch_counts_for_column, merge_batch_refs

_PRODUCT_MAPPING_ENTITY_TYPES = ("product_identifier",)


async def _batch_product_roadmap_counts(db: AsyncSession, product_ids: list[int]) -> dict[int, int]:
    ids = [int(i) for i in product_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    out: dict[int, int] = {i: 0 for i in ids}
    for col in (
        FactProductRoadmap.product_id,
        FactProductRoadmap.replacement_candidate_id,
    ):
        for pid, cnt in (await batch_counts_for_column(db, col, ids)).items():
            out[pid] = out.get(pid, 0) + cnt
    return {pid: n for pid, n in out.items() if n > 0}


async def _batch_lineup_product_counts(db: AsyncSession, product_ids: list[int]) -> dict[int, int]:
    ids = [int(i) for i in product_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    out: dict[int, int] = {i: 0 for i in ids}
    for col in (
        FactLineupPlanItem.product_id,
        FactLineupPlanItem.predecessor_product_id,
        FactLineupPlanItem.successor_product_id,
    ):
        for pid, cnt in (await batch_counts_for_column(db, col, ids)).items():
            out[pid] = out.get(pid, 0) + cnt
    return {pid: n for pid, n in out.items() if n > 0}


async def _batch_mapping_candidate_counts(db: AsyncSession, product_ids: list[int]) -> dict[int, int]:
    ids = [int(i) for i in product_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    col = ImportEntityMappingCandidate.suggested_entity_id
    stmt = (
        select(col, func.count())
        .where(
            col.in_(ids),
            ImportEntityMappingCandidate.entity_type.in_(_PRODUCT_MAPPING_ENTITY_TYPES),
        )
        .group_by(col)
    )
    rows = (await db.execute(stmt)).all()
    return {int(k): int(v) for k, v in rows if k is not None}


async def product_hard_reference_breakdown_batch(
    db: AsyncSession, product_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in product_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out

    specs: list[tuple[str, object]] = [
        ("Sell-out", FactSalesSellout.product_id),
        ("Sell-in", FactSalesSellin.product_id),
        ("Customer inventory", FactInventoryCustomer.product_id),
        ("Distributor inventory", FactInventoryDistributor.product_id),
        ("Inbound shipments", FactInboundShipment.product_id),
        ("Pricing", FactPricing.product_id),
        ("Support / MDF", FactSupport.product_id),
        ("Promotion plans", FactPromotionPlan.product_id),
        ("Promotion performance", FactPromotionPerformance.product_id),
        ("Forecasts", FactForecast.product_id),
        ("Buy plans", FactBuyPlan.product_id),
        ("Competitor mappings", FactCompetitorMapping.product_id),
        ("Budget requests (linked SKU)", FactBudgetRequest.linked_product_id),
        ("Activation", FactActivation.product_id),
        ("Customer sell-through", FactCustomerSellthrough.product_id),
        ("Customer velocity", FactCustomerVelocity.product_id),
        ("DSI forecasts", FactDsiForecast.product_id),
        ("Shipment evidence (resolved product)", ShipmentEvidenceLine.product_id),
        ("DSI import staging (resolved product)", ImportDistributorSiStagingLine.resolved_product_id),
        ("Customer sell-through import staging", ImportCustomerSellthroughStagingLine.resolved_product_id),
        ("Catalog products (canonical link)", CatalogProduct.canonical_product_id),
        ("Commercial SKU assumptions", CommercialSkuAssumption.product_id),
    ]
    for label, col in specs:
        merge_batch_refs(out, ids, label, await batch_counts_for_column(db, col, ids))

    merge_batch_refs(out, ids, "Product roadmap", await _batch_product_roadmap_counts(db, ids))
    merge_batch_refs(out, ids, "Lineup plan items", await _batch_lineup_product_counts(db, ids))
    merge_batch_refs(
        out,
        ids,
        "Import mapping candidates (product)",
        await _batch_mapping_candidate_counts(db, ids),
    )
    return out


async def cleanup_soft_product_references(db: AsyncSession, product_id: int) -> None:
    """Delete derived / auxiliary rows so dim_product delete is not blocked by them."""
    await db.execute(delete(BuyRecommendation).where(BuyRecommendation.product_id == product_id))
    await db.execute(delete(PricingRecommendation).where(PricingRecommendation.product_id == product_id))
    await db.execute(delete(PromoReadiness).where(PromoReadiness.product_id == product_id))
    await db.execute(delete(CompetitivePositioning).where(CompetitivePositioning.product_id == product_id))
    await db.execute(delete(StockRisk).where(StockRisk.product_id == product_id))
    await db.execute(delete(WeeksOfStock).where(WeeksOfStock.product_id == product_id))
    await db.execute(delete(StockHealth).where(StockHealth.product_id == product_id))
    await db.execute(delete(ForecastSummary).where(ForecastSummary.product_id == product_id))
    await db.execute(delete(ProductAlias).where(ProductAlias.product_id == product_id))
    await db.execute(delete(ExceptionInboxItem).where(ExceptionInboxItem.product_id == product_id))


async def product_hard_reference_breakdown(db: AsyncSession, product_id: int) -> list[dict[str, int | str]]:
    batch = await product_hard_reference_breakdown_batch(db, [product_id])
    return batch.get(product_id, [])


async def product_reference_breakdown(db: AsyncSession, product_id: int) -> list[dict[str, int | str]]:
    return await product_hard_reference_breakdown(db, product_id)
