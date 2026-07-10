"""Listing Capture v0 models (LC-U1) — registry + observations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class CustomerListing(Base, TimestampMixin):
    """Registered customer marketplace listing URL. Status observed — never hard-deleted."""

    __tablename__ = "customer_listing"
    __table_args__ = (
        UniqueConstraint("customer_id", "url", name="uq_customer_listing_customer_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    registered_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    observations: Mapped[list["ListingObservation"]] = relationship(
        "ListingObservation", back_populates="listing"
    )


class ListingObservation(Base, TimestampMixin):
    """Fetched snapshot for a listing. Parse failure retains snapshot (FLAG≠BLOCK)."""

    __tablename__ = "listing_observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("customer_listing.id"), nullable=False, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_snapshot: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    extracted_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    extracted_availability: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_promo_badge: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    parse_flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    listing: Mapped["CustomerListing"] = relationship("CustomerListing", back_populates="observations")
