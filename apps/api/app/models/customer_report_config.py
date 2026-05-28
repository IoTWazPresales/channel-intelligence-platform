"""Per-customer sell-through report cadence and structure configuration."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomerReportConfig(Base, TimestampMixin):
    """One config row per customer for sell-through reporting expectations."""

    __tablename__ = "customer_report_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, unique=True)
    reports_expected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expected_cadence: Mapped[str] = mapped_column(String(16), nullable=False, default="weekly")
    report_structure_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_report_received: Mapped[date | None] = mapped_column(Date, nullable=True)
    overdue_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
