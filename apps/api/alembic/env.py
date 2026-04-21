from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.sync_url import sqlalchemy_sync_engine_url
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
    FactLineupPlanItem,
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
    ImportTemplate,
    LineupGapAnalysis,
    PricingRecommendation,
    ProductAlias,
    PromoPlanExport,
    PromoPlanExportEvent,
    PromoReadiness,
    RawFileMetadata,
    RoadmapRecommendation,
    SourceDefinition,
    StockHealth,
    StockRisk,
    WeeksOfStock,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return sqlalchemy_sync_engine_url(get_settings().database_url_sync)


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), pool_pre_ping=True)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
