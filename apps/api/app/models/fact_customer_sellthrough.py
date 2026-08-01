"""Customer sell-through fact rows (retailer POS / chain reports)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FactCustomerSellthrough(Base, TimestampMixin):
    """Sell-through at chain or store grain for a product and period start."""

    __tablename__ = "fact_customer_sellthrough"
    __table_args__ = (
        Index("ix_fact_customer_sellthrough_customer_period", "customer_id", "period_start_date"),
        Index("ix_fact_customer_sellthrough_product_period", "product_id", "period_start_date"),
        Index(
            "ix_fact_customer_sellthrough_location_product_period",
            "customer_location_id",
            "product_id",
            "period_start_date",
            postgresql_where="customer_location_id IS NOT NULL",
        ),
        Index("ix_fact_customer_sellthrough_import_job", "import_job_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default", index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    customer_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_location.id"), nullable=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    period_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(8), nullable=False)
    units_sold: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    raw_mtd_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_mtd_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit_sell_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_mac: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    reported_soh: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    site_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    vat_basis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
    raw_source_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
