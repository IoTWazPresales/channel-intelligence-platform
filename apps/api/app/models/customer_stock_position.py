"""Expected customer stock position beside the reported on-hand (N-0110).

Derived and recomputed from fact_customer_sellthrough and fact_inbound_shipment.
Never edits either source. One row per customer, product and report period.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerStockPosition(Base):
    __tablename__ = "customer_stock_position"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id", ondelete="CASCADE"), nullable=False)
    period_grain: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    period_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    report_import_job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
    reported_on_hand: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    units_sold: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    in_transit_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    on_order_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    previous_period_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_on_hand: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    receipts_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    expected_on_hand: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    gap_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
