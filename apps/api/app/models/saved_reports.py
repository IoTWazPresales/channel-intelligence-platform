"""P3-4 saved reports and dashboards."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SavedReport(Base):
    __tablename__ = "saved_report"
    __table_args__ = (
        CheckConstraint("visibility IN ('personal', 'published')", name="ck_saved_report_visibility"),
        CheckConstraint("visual IN ('kpi', 'table', 'bar')", name="ck_saved_report_visual"),
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

    tiles: Mapped[list["DashboardTile"]] = relationship(
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="DashboardTile.sort_order",
    )


class DashboardTile(Base):
    __tablename__ = "dashboard_tile"
    __table_args__ = (
        UniqueConstraint("dashboard_id", "saved_report_id", name="uq_dashboard_tile_report"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dashboard_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("dashboard.id", ondelete="CASCADE"), nullable=False, index=True
    )
    saved_report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("saved_report.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    title_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    dashboard: Mapped[Dashboard] = relationship(back_populates="tiles")
    saved_report: Mapped[SavedReport | None] = relationship()
