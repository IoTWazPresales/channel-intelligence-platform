from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class LineupPlanItemEvent(Base):
    """Audit trail when line-up approval_status changes (and optional notes snapshot)."""

    __tablename__ = "lineup_plan_item_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lineup_item_id: Mapped[int] = mapped_column(
        ForeignKey("fact_lineup_plan_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), default="approval_changed", nullable=False)
    old_approval_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_approval_status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    lineup_item: Mapped["FactLineupPlanItem"] = relationship("FactLineupPlanItem", back_populates="approval_events")


class FactLineupPlanItem(Base, TimestampMixin):
    """Customer/channel/period-scoped line-up planning (distinct from portfolio roadmap)."""

    __tablename__ = "fact_lineup_plan_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str | None] = mapped_column(String(32), nullable=True)

    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    predecessor_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    successor_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)

    current_range_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    planned_range_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    planned_launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_eol_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    current_volume_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    planned_volume_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)

    overlap_cannibalization_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whitespace_gap_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    approval_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    link_buy_plan_id: Mapped[int | None] = mapped_column(ForeignKey("fact_buy_plan.id"), nullable=True)
    link_pricing_id: Mapped[int | None] = mapped_column(ForeignKey("fact_pricing.id"), nullable=True)
    link_promotion_id: Mapped[int | None] = mapped_column(ForeignKey("dim_promotion.id"), nullable=True)
    link_budget_request_id: Mapped[int | None] = mapped_column(ForeignKey("fact_budget_request.id"), nullable=True)
    link_roadmap_id: Mapped[int | None] = mapped_column(ForeignKey("fact_product_roadmap.id"), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer = relationship("DimCustomer", foreign_keys=[customer_id])
    channel = relationship("DimChannel", foreign_keys=[channel_id])
    product = relationship("DimProduct", foreign_keys=[product_id])
    predecessor_product = relationship("DimProduct", foreign_keys=[predecessor_product_id])
    successor_product = relationship("DimProduct", foreign_keys=[successor_product_id])
    approval_events: Mapped[list["LineupPlanItemEvent"]] = relationship(
        "LineupPlanItemEvent",
        back_populates="lineup_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
