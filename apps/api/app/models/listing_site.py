"""Listing sites and each customer's seller identity per site (tenant data, edited in the app)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ListingSite(Base, TimestampMixin):
    """A retailer site CIP reads product pages from. ``site_key`` is ``customer_listing.marketplace``."""

    __tablename__ = "listing_site"
    __table_args__ = (UniqueConstraint("tenant_id", "site_key", name="uq_listing_site_tenant_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    site_key: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_url_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_id_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_url_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_url_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_party_seller: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rate_limit_seconds: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)

    sellers: Mapped[list["ListingSiteSeller"]] = relationship(
        "ListingSiteSeller", back_populates="site", cascade="all, delete-orphan"
    )


class ListingSiteSeller(Base, TimestampMixin):
    """A customer that sells on a site, with its own seller names and ids there."""

    __tablename__ = "listing_site_seller"
    __table_args__ = (
        UniqueConstraint("site_id", "customer_id", name="uq_listing_site_seller_site_customer"),
        Index("ix_listing_site_seller_customer", "customer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    site_id: Mapped[int] = mapped_column(ForeignKey("listing_site.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    seller_names: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    seller_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)

    site: Mapped["ListingSite"] = relationship("ListingSite", back_populates="sellers")
