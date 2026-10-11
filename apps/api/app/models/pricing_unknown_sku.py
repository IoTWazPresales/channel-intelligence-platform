"""Price entries whose SKU is not in the product master.

A row here is the steward queue item. It is not a product and not a price fact.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PricingUnknownSku(Base, TimestampMixin):
    __tablename__ = "pricing_unknown_sku"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    list_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    net_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
