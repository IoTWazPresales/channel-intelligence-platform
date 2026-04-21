from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FactSalesSellout(Base, TimestampMixin):
    __tablename__ = "fact_sales_sellout"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    revenue: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class FactSalesSellin(Base, TimestampMixin):
    __tablename__ = "fact_sales_sellin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    revenue: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class FactInventoryCustomer(Base, TimestampMixin):
    __tablename__ = "fact_inventory_customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    on_hand_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    on_order_units: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)


class FactInventoryDistributor(Base, TimestampMixin):
    __tablename__ = "fact_inventory_distributor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    on_hand_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class FactInboundShipment(Base, TimestampMixin):
    __tablename__ = "fact_inbound_shipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)
    eta_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", nullable=False)


class FactPricing(Base, TimestampMixin):
    __tablename__ = "fact_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    list_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    net_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)


class FactSupport(Base, TimestampMixin):
    __tablename__ = "fact_support"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    support_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    support_type: Mapped[str] = mapped_column(String(64), nullable=False)


class FactPromotionPlan(Base, TimestampMixin):
    __tablename__ = "fact_promotion_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("dim_promotion.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    expected_uplift_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    support_needed: Mapped[str | None] = mapped_column(Text, nullable=True)
    stock_readiness: Mapped[str | None] = mapped_column(String(64), nullable=True)


class FactPromotionPerformance(Base, TimestampMixin):
    __tablename__ = "fact_promotion_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("dim_promotion.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    lift_actual_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactMarketShare(Base, TimestampMixin):
    __tablename__ = "fact_market_share"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(256), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    share_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    panel_source: Mapped[str | None] = mapped_column(String(128), nullable=True)


class FactActivation(Base, TimestampMixin):
    __tablename__ = "fact_activation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    activation_score: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)


class FactForecast(Base, TimestampMixin):
    __tablename__ = "fact_forecast"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    confidence_placeholder: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FactBuyPlan(Base, TimestampMixin):
    __tablename__ = "fact_buy_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)
    recommended_qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    recommended_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    recommended_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    risk_if_not_ordered: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactCompetitorMapping(Base, TimestampMixin):
    __tablename__ = "fact_competitor_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    competitor_product_id: Mapped[int] = mapped_column(
        ForeignKey("dim_competitor_product.id"), nullable=False
    )
    score: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)


class FactCompetitorPrice(Base, TimestampMixin):
    __tablename__ = "fact_competitor_price"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competitor_product_id: Mapped[int] = mapped_column(
        ForeignKey("dim_competitor_product.id"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    channel: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("import_job.id"), nullable=True)


class FactProductRoadmap(Base, TimestampMixin):
    __tablename__ = "fact_product_roadmap"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    lifecycle_phase: Mapped[str] = mapped_column(String(64), nullable=False)
    replacement_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_product.id"), nullable=True
    )
    launch_target: Mapped[date | None] = mapped_column(Date, nullable=True)
    retire_target: Mapped[date | None] = mapped_column(Date, nullable=True)
    whitespace_flag: Mapped[bool] = mapped_column(default=False, nullable=False)
    overlap_flag: Mapped[bool] = mapped_column(default=False, nullable=False)


class FactBudgetAllocation(Base, TimestampMixin):
    __tablename__ = "fact_budget_allocation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("dim_budget_owner.id"), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    envelope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    allocated_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class FactBudgetCommitment(Base, TimestampMixin):
    __tablename__ = "fact_budget_commitment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("dim_budget_owner.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    committed_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactBudgetActual(Base, TimestampMixin):
    __tablename__ = "fact_budget_actual"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("dim_budget_owner.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    actual_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)


class FactBudgetRequest(Base, TimestampMixin):
    __tablename__ = "fact_budget_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("dim_budget_owner.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    initiative_type: Mapped[str] = mapped_column(String(64), nullable=False)
    linked_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    linked_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_customer.id"), nullable=True
    )
    linked_promotion_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_promotion.id"), nullable=True
    )
    linked_roadmap_id: Mapped[int | None] = mapped_column(
        ForeignKey("fact_product_roadmap.id"), nullable=True
    )
    justification_summary: Mapped[str] = mapped_column(Text, nullable=False)
    expected_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_of_not_funding: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
