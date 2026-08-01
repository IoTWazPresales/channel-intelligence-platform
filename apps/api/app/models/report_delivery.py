"""P3-5 report delivery inbox + schedules."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReportDelivery(Base):
    __tablename__ = "report_delivery"
    __table_args__ = (
        CheckConstraint("channel IN ('inbox', 'email_stub')", name="ck_report_delivery_channel"),
        CheckConstraint(
            "trigger IN ('manual', 'schedule', 'import_event')",
            name="ck_report_delivery_trigger",
        ),
        CheckConstraint("format IN ('xlsx', 'pdf')", name="ck_report_delivery_format"),
        CheckConstraint("status IN ('delivered', 'failed')", name="ck_report_delivery_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recipient_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    saved_report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("saved_report.id", ondelete="SET NULL"), nullable=True
    )
    dashboard_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("dashboard.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="inbox", server_default="inbox")
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="manual", server_default="manual")
    format: Mapped[str] = mapped_column(Text, nullable=False, default="xlsx", server_default="xlsx")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="delivered", server_default="delivered")
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_vintage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    missing_data_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    metric_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class ReportSchedule(Base):
    __tablename__ = "report_schedule"
    __table_args__ = (
        CheckConstraint(
            "cadence IN ('weekly_monday_0700', 'daily_0700', 'on_import_complete')",
            name="ck_report_schedule_cadence",
        ),
        CheckConstraint("format IN ('xlsx', 'pdf')", name="ck_report_schedule_format"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    saved_report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("saved_report.id", ondelete="CASCADE"), nullable=True
    )
    dashboard_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("dashboard.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    cadence: Mapped[str] = mapped_column(
        Text, nullable=False, default="weekly_monday_0700", server_default="weekly_monday_0700"
    )
    format: Mapped[str] = mapped_column(Text, nullable=False, default="xlsx", server_default="xlsx")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    subscriber_user_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
