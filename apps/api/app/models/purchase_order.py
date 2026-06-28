"""Purchase order entity — observed from shipment evidence or declared in lineup."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

PURCHASE_ORDER_STATUSES: tuple[str, ...] = ("observed", "raised", "amended", "closed")
PURCHASE_ORDER_SOURCES: tuple[str, ...] = ("shipment_materialized", "steward", "lineup_declared")


class PurchaseOrder(Base, TimestampMixin):
    """Normalised distributor/customer PO number anchored to a distributor when known."""

    __tablename__ = "purchase_order"
    __table_args__ = (
        UniqueConstraint(
            "po_number_norm",
            "distributor_id",
            name="uq_purchase_order_norm_distributor",
        ),
        Index("ix_purchase_order_po_number_norm", "po_number_norm"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_number_raw: Mapped[str] = mapped_column(String(128), nullable=False)
    po_number_norm: Mapped[str] = mapped_column(String(128), nullable=False)
    distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="observed", nullable=False)
    dismiss_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="shipment_materialized", nullable=False)
