"""Product delete: hard blockers vs derived rows that are auto-cleaned.

All hard-reference checks are executed as a single UNION ALL query — one
network round trip to the database regardless of the number of tables checked.
"""

from __future__ import annotations

from sqlalchemy import Select, delete, func, literal, select
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
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)

EV = shipment_evidence_read_model()
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_PRODUCT_MAPPING_ENTITY_TYPES = ("product_identifier",)

_SPECS: list[tuple[str, object]] = [
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
    ("Shipment evidence (resolved product)", EV.product_id),
    ("DSI import staging (resolved product)", ImportDistributorSiStagingLine.resolved_product_id),
    ("Customer sell-through import staging", ImportCustomerSellthroughStagingLine.resolved_product_id),
    ("Catalog products (canonical link)", CatalogProduct.canonical_product_id),
    ("Commercial SKU assumptions", CommercialSkuAssumption.product_id),
]


def _extra_product_subqueries(ids: list[int]) -> list[Select]:
    """Additional subqueries for multi-column or filtered reference checks."""
    return [
        # Roadmap references products as primary SKU or as replacement candidate.
        # The two columns are merged into a single count per entity.
        count_subquery_for_columns(
            "Product roadmap",
            [FactProductRoadmap.product_id, FactProductRoadmap.replacement_candidate_id],
            ids,
        ),
        # Lineup items reference products in three roles; aggregate all three.
        count_subquery_for_columns(
            "Lineup plan items",
            [
                FactLineupPlanItem.product_id,
                FactLineupPlanItem.predecessor_product_id,
                FactLineupPlanItem.successor_product_id,
            ],
            ids,
        ),
        # Mapping candidates restricted to product entity types.
        select(
            literal("Import mapping candidates (product)").label("lbl"),
            ImportEntityMappingCandidate.suggested_entity_id.label("entity_id"),
            func.count().label("cnt"),
        )
        .where(
            ImportEntityMappingCandidate.suggested_entity_id.in_(ids),
            ImportEntityMappingCandidate.entity_type.in_(_PRODUCT_MAPPING_ENTITY_TYPES),
        )
        .group_by(ImportEntityMappingCandidate.suggested_entity_id),
    ]


async def product_hard_reference_breakdown_batch(
    db: AsyncSession, product_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in product_ids if isinstance(i, int) and i > 0]
    out: dict[int, list[dict[str, int | str]]] = {i: [] for i in ids}
    if not ids:
        return out
    subqueries = []
    for label, col in _SPECS:
        sq = count_subquery_for_columns(label, [col], ids)
        if label.startswith("Shipment evidence"):
            sq = apply_active_evidence_filter(sq, model=EV)
        subqueries.append(sq)
    subqueries.extend(_extra_product_subqueries(ids))
    return await batch_counts_multi_table(db, subqueries, ids)


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


async def product_hard_reference_breakdown(
    db: AsyncSession, product_id: int
) -> list[dict[str, int | str]]:
    batch = await product_hard_reference_breakdown_batch(db, [product_id])
    return batch.get(product_id, [])


async def product_reference_breakdown(
    db: AsyncSession, product_id: int
) -> list[dict[str, int | str]]:
    return await product_hard_reference_breakdown(db, product_id)
