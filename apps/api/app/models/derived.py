from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RecommendationMixin, TimestampMixin


class StockHealth(Base, TimestampMixin):
    __tablename__ = "stock_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    health_state: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)


class WeeksOfStock(Base, TimestampMixin):
    __tablename__ = "weeks_of_stock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    wos: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    target_wos: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)


class StockRisk(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "stock_risk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    risk_kind: Mapped[str] = mapped_column(String(32), nullable=False)


class ForecastSummary(Base, TimestampMixin):
    __tablename__ = "forecast_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    accuracy_placeholder: Mapped[str | None] = mapped_column(String(128), nullable=True)


class BuyRecommendation(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "buy_recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    buy_plan_id: Mapped[int | None] = mapped_column(ForeignKey("fact_buy_plan.id"), nullable=True)


class PricingRecommendation(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "pricing_recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    suggested_state: Mapped[str] = mapped_column(String(64), nullable=False)


class PromoReadiness(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "promo_readiness"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("dim_promotion.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)


class CompetitivePositioning(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "competitive_positioning"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    competitor_product_id: Mapped[int] = mapped_column(
        ForeignKey("dim_competitor_product.id"), nullable=False
    )


class LineupGapAnalysis(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "lineup_gap_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roadmap_id: Mapped[int] = mapped_column(ForeignKey("fact_product_roadmap.id"), nullable=False)


class RoadmapRecommendation(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "roadmap_recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roadmap_id: Mapped[int] = mapped_column(ForeignKey("fact_product_roadmap.id"), nullable=False)


class BudgetHealth(Base, TimestampMixin):
    __tablename__ = "budget_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("dim_budget_owner.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    remaining_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    pressure_state: Mapped[str] = mapped_column(String(32), nullable=False)


class BudgetJustificationSummary(Base, RecommendationMixin, TimestampMixin):
    __tablename__ = "budget_justification_summary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_request_id: Mapped[int] = mapped_column(ForeignKey("fact_budget_request.id"), nullable=False)
    recommended_budget_delta: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)


class ExceptionInboxItem(Base, TimestampMixin):
    """Action queue: stockout, mapping, price conflict, etc."""

    __tablename__ = "exception_inbox_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exception_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
