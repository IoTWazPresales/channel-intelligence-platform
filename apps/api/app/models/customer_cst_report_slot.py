"""Expected CST report tracker slots (due / late / missing / received)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomerCstReportSlot(Base, TimestampMixin):
    """One expected-report slot per customer × week_start."""

    __tablename__ = "customer_cst_report_slot"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "week_start_date",
            name="uq_customer_cst_report_slot_customer_week",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="due")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
    cadence_snapshot: Mapped[str | None] = mapped_column(String(16), nullable=True)
