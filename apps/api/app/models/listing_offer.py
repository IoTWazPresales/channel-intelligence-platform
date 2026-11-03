"""Every offer captured with an observation. The buy-box row is the shopper's price."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingOffer(Base):
    __tablename__ = "listing_offer"
    __table_args__ = (
        Index("ix_listing_offer_observation", "observation_id"),
        Index("ix_listing_offer_listing", "listing_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    observation_id: Mapped[int] = mapped_column(ForeignKey("listing_observation.id", ondelete="CASCADE"), nullable=False)
    listing_id: Mapped[int] = mapped_column(ForeignKey("customer_listing.id", ondelete="CASCADE"), nullable=False)
    seller_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    seller_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_buy_box: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_own_seller: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    offer_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(64), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
