"""A customer's web shop domain: a proposal, a confirmed site, or a remembered rejection.

``status = 'proposed'`` is the site-candidate steward queue. Confirm and reject are both
remembered, so a rejected domain is not proposed again for that customer. The table works for any
customer, reporting or not. Nothing here names a customer, retailer or country.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

WEB_SITE_PROPOSED = "proposed"
WEB_SITE_CONFIRMED = "confirmed"
WEB_SITE_REJECTED = "rejected"

WEB_SOURCE_AUTO = "auto"
WEB_SOURCE_STEWARD = "steward"
WEB_SOURCE_USER = "user"


class CustomerWebSite(Base, TimestampMixin):
    __tablename__ = "customer_web_site"
    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", "domain", name="uq_customer_web_site_tenant_customer_domain"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_customer_web_site_status"),
        CheckConstraint("source IN ('auto', 'steward', 'user')", name="ck_customer_web_site_source"),
        Index("ix_customer_web_site_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("listing_site.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    preview_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
