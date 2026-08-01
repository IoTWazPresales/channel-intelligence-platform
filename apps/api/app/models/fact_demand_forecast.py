"""Demand forecast contract — sole B2/B4 consumable forecast table (B1)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FactDemandForecast(Base, TimestampMixin):
    """Atomic demand forecast at distributor × product × customer × period.

    ``fact_dsi_forecast`` is an upstream velocity projection cache only.
    Legacy ``fact_forecast`` rows migrate here as ``method='manual'`` overrides.
    """

    __tablename__ = "fact_demand_forecast"
    __table_args__ = (
        UniqueConstraint(
            "distributor_id",
            "product_id",
            "customer_id",
            "period_start",
            name="uq_fact_demand_forecast_grain",
        ),
        Index("ix_fact_demand_forecast_tenant", "tenant_id"),
        Index("ix_fact_demand_forecast_period", "period_start"),
        Index(
            "ix_fact_demand_forecast_dist_prod",
            "distributor_id",
            "product_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)

    forecast_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    lower_band: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    upper_band: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)

    # velocity | analogue | manual | blend
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    # low | medium | high | override
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False)

    velocity_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seasonal_index: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    analogue_product_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_product.id"), nullable=True
    )
    analogue_basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    is_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
