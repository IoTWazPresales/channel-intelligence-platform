"""P3-4 saved reports and first-class dashboard widgets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SavedReport(Base):
    __tablename__ = "saved_report"
    __table_args__ = (
        CheckConstraint("visibility IN ('personal', 'published')", name="ck_saved_report_visibility"),
        CheckConstraint(
            "visual IN ('kpi', 'table', 'bar', 'line', 'area')",
            name="ck_saved_report_visual",
        ),
        CheckConstraint(
            "period_grain IS NULL OR period_grain IN ('week', 'month', 'quarter')",
            name="ck_saved_report_period_grain",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(Text, nullable=False, default="personal", server_default="personal")
    shared_roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    grains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    visual: Mapped[str] = mapped_column(Text, nullable=False, default="kpi", server_default="kpi")
    period_grain: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Dashboard(Base):
    __tablename__ = "dashboard"
    __table_args__ = (
        CheckConstraint("visibility IN ('personal', 'published')", name="ck_dashboard_visibility"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(Text, nullable=False, default="personal", server_default="personal")
    shared_roles: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    widgets: Mapped[list["DashboardWidget"]] = relationship(
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardWidget.sort_order",
    )


class DashboardWidget(Base):
    __tablename__ = "dashboard_widget"
    __table_args__ = (
        CheckConstraint(
            "visual IN ('kpi', 'table', 'bar', 'line', 'area')",
            name="ck_dashboard_widget_visual",
        ),
        CheckConstraint(
            "period_grain IS NULL OR period_grain IN ('week', 'month', 'quarter')",
            name="ck_dashboard_widget_period_grain",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dashboard_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dashboard.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    visual: Mapped[str] = mapped_column(Text, nullable=False, default="kpi", server_default="kpi")
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    grains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    period_grain: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    saved_report_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("saved_report.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    dashboard: Mapped[Dashboard] = relationship(back_populates="widgets")
    saved_report: Mapped[SavedReport | None] = relationship()
