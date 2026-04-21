"""Product delete: hard blockers vs derived rows that are auto-cleaned."""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.lineup import FactLineupPlanItem
from app.models.mapping import ProductAlias

# ---------------------------------------------------------------------------
# Classification (audit)
#
# Hard blockers — true business / source / planning facts that must be removed
# or reassigned before deleting dim_product:
#   Sell-out, Sell-in, inventories, inbound, pricing, support/MDF, promo plans
#   & performance, forecasts, buy plans, competitor mappings, roadmap rows,
#   budget requests (linked SKU), activation, lineup (SKU / pred / succ).
#
# Soft cleanup — derived, generated, or ingest-adjacent rows removed when the
# product is deleted (no 409):
#   Stock health, weeks of stock, stock risk, buy/pricing/promo/competitive
#   recommendations, forecast summary, product aliases, exception inbox rows
#   tied to this product_id.
#
# Not keyed to dim_product (no delete impact here): budget_health, market
# share, competitor_price, promo_plan_export, entity_mapping_queue (no FK).
# ---------------------------------------------------------------------------


def _hard_reference_checks(product_id: int) -> list[tuple[str, object]]:
    return [
        ("Sell-out", select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.product_id == product_id)),
        ("Sell-in", select(func.count()).select_from(FactSalesSellin).where(FactSalesSellin.product_id == product_id)),
        (
            "Customer inventory",
            select(func.count()).select_from(FactInventoryCustomer).where(FactInventoryCustomer.product_id == product_id),
        ),
        (
            "Distributor inventory",
            select(func.count())
            .select_from(FactInventoryDistributor)
            .where(FactInventoryDistributor.product_id == product_id),
        ),
        (
            "Inbound shipments",
            select(func.count()).select_from(FactInboundShipment).where(FactInboundShipment.product_id == product_id),
        ),
        ("Pricing", select(func.count()).select_from(FactPricing).where(FactPricing.product_id == product_id)),
        ("Support / MDF", select(func.count()).select_from(FactSupport).where(FactSupport.product_id == product_id)),
        (
            "Promotion plans",
            select(func.count()).select_from(FactPromotionPlan).where(FactPromotionPlan.product_id == product_id),
        ),
        (
            "Promotion performance",
            select(func.count())
            .select_from(FactPromotionPerformance)
            .where(FactPromotionPerformance.product_id == product_id),
        ),
        ("Forecasts", select(func.count()).select_from(FactForecast).where(FactForecast.product_id == product_id)),
        ("Buy plans", select(func.count()).select_from(FactBuyPlan).where(FactBuyPlan.product_id == product_id)),
        (
            "Competitor mappings",
            select(func.count()).select_from(FactCompetitorMapping).where(FactCompetitorMapping.product_id == product_id),
        ),
        (
            "Product roadmap",
            select(func.count())
            .select_from(FactProductRoadmap)
            .where(
                or_(
                    FactProductRoadmap.product_id == product_id,
                    FactProductRoadmap.replacement_candidate_id == product_id,
                )
            ),
        ),
        (
            "Budget requests (linked SKU)",
            select(func.count())
            .select_from(FactBudgetRequest)
            .where(FactBudgetRequest.linked_product_id == product_id),
        ),
        ("Activation", select(func.count()).select_from(FactActivation).where(FactActivation.product_id == product_id)),
        (
            "Lineup plan items",
            select(func.count())
            .select_from(FactLineupPlanItem)
            .where(
                or_(
                    FactLineupPlanItem.product_id == product_id,
                    FactLineupPlanItem.predecessor_product_id == product_id,
                    FactLineupPlanItem.successor_product_id == product_id,
                )
            ),
        ),
    ]


async def cleanup_soft_product_references(db: AsyncSession, product_id: int) -> None:
    """Delete derived / auxiliary rows so dim_product delete is not blocked by them."""
    # Order: recommendation-like rows first, then metrics, aliases, inbox.
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
    """Return `{label, count}` for dependencies that still block product delete."""
    out: list[dict[str, int | str]] = []
    for label, stmt in _hard_reference_checks(product_id):
        n = (await db.execute(stmt)).scalar_one()
        if int(n) > 0:
            out.append({"label": label, "count": int(n)})
    return out


async def product_reference_breakdown(db: AsyncSession, product_id: int) -> list[dict[str, int | str]]:
    """Same as `product_hard_reference_breakdown` (used by GET references & delete UX)."""
    return await product_hard_reference_breakdown(db, product_id)
