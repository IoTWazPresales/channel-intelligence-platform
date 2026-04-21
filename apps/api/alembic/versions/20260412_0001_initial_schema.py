"""Initial schema from SQLAlchemy models.

Revision ID: 20260412_0001
Revises:
Create Date: 2026-04-12

"""

from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.models import (  # noqa: F401
    BudgetHealth,
    BudgetJustificationSummary,
    BuyRecommendation,
    CompetitivePositioning,
    DimBudgetOwner,
    DimChannel,
    DimCompetitorBrand,
    DimCompetitorProduct,
    DimCustomer,
    DimDate,
    DimDistributor,
    DimProduct,
    DimPromotion,
    DimRegion,
    DimSource,
    EntityMappingQueue,
    ExceptionInboxItem,
    FactActivation,
    FactBudgetActual,
    FactBudgetAllocation,
    FactBudgetCommitment,
    FactBudgetRequest,
    FactBuyPlan,
    FactCompetitorMapping,
    FactCompetitorPrice,
    FactForecast,
    FactInboundShipment,
    FactInventoryCustomer,
    FactInventoryDistributor,
    FactMarketShare,
    FactPricing,
    FactProductRoadmap,
    FactPromotionPerformance,
    FactPromotionPlan,
    FactSalesSellin,
    FactSalesSellout,
    FactSupport,
    ForecastSummary,
    ImportJob,
    ImportRowResult,
    LineupGapAnalysis,
    PricingRecommendation,
    ProductAlias,
    PromoReadiness,
    RawFileMetadata,
    RoadmapRecommendation,
    SourceDefinition,
    StockHealth,
    StockRisk,
    WeeksOfStock,
)

revision: str = "20260412_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
