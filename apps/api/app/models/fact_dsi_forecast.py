from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FactDsiForecast(Base):
    """DSI-generated distributor/product forecasts (not Commercial Planner ``fact_forecast``)."""

    __tablename__ = "fact_dsi_forecast"
    __table_args__ = (
        Index("ix_fact_dsi_forecast_dist_date", "distributor_id", "forecast_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    upper_band: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    lower_band: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    velocity_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
