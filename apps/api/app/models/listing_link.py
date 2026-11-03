"""Remembered product-page links and the steward queue for ones that could not be confirmed."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

LINK_CONFIRMED = "confirmed"
LINK_REJECTED = "rejected"
LINK_STALE = "stale"

QUEUE_OPEN = "open"
QUEUE_CONFIRMED = "confirmed"
QUEUE_REJECTED = "rejected"
QUEUE_NOT_ON_SITE = "not_on_site"


class ListingLink(Base, TimestampMixin):
    """One decision for a product page on a site. Confirm and reject are both remembered."""

    __tablename__ = "listing_link"
    __table_args__ = (
        UniqueConstraint("site_id", "product_id", "url", name="uq_listing_link_site_product_url"),
        CheckConstraint("status IN ('confirmed', 'rejected', 'stale')", name="ck_listing_link_status"),
        Index("uq_listing_link_one_confirmed", "site_id", "product_id", unique=True, postgresql_where="status = 'confirmed'"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    site_id: Mapped[int] = mapped_column(ForeignKey("listing_site.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    decided_by: Mapped[str | None] = mapped_column(String(256), nullable=True)


class ListingLinkQueue(Base, TimestampMixin):
    """A product page the reader could not confirm. A steward decides once."""

    __tablename__ = "listing_link_queue"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'confirmed', 'rejected', 'not_on_site')",
            name="ck_listing_link_queue_status",
        ),
        Index("uq_listing_link_queue_open", "site_id", "product_id", unique=True, postgresql_where="status = 'open'"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    site_id: Mapped[int] = mapped_column(ForeignKey("listing_site.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("customer_listing.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    candidates: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=QUEUE_OPEN, server_default=QUEUE_OPEN)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
