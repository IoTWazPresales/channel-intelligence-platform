"""Store and DC replenishment. Candidates are not master rows.

An import may insert a candidate. It must not insert a customer, a distributor,
a product, or a location. A steward confirms or rejects once.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SiteCandidate(Base, TimestampMixin):
    """One question about a site label. Confirm and reject are both remembered."""

    __tablename__ = "site_candidate"
    __table_args__ = (
        CheckConstraint(
            "evidence_kind IN ('pattern', 'stock_behaviour', 'direct_shipment')",
            name="ck_site_candidate_kind",
        ),
        CheckConstraint(
            "status IN ('open', 'confirmed', 'rejected')",
            name="ck_site_candidate_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default", index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id", ondelete="CASCADE"), nullable=True)
    distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id", ondelete="SET NULL"), nullable=True
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_location.id", ondelete="SET NULL"), nullable=True
    )
    site_label: Mapped[str] = mapped_column(Text, nullable=False)
    site_label_norm: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    blocked_as_distributor_site: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class DcServedAccount(Base):
    """Explicit list of customer accounts a confirmed DC serves. Not a name match."""

    __tablename__ = "dc_served_account"
    __table_args__ = (
        CheckConstraint(
            "candidate_id IS NOT NULL",
            name="ck_dc_served_account_candidate",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    candidate_id: Mapped[int] = mapped_column(ForeignKey("site_candidate.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StoreDcTenantConfig(Base, TimestampMixin):
    """Tenant configuration for this module. Empty row means the code fallbacks."""

    __tablename__ = "store_dc_tenant_config"
    __table_args__ = (
        CheckConstraint(
            "lead_time_min_deliveries >= 1 AND lead_time_min_deliveries <= 1000",
            name="ck_store_dc_min_deliveries",
        ),
        CheckConstraint(
            "stock_behaviour_min_soh > 0",
            name="ck_store_dc_stock_min_soh",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    lead_time_min_deliveries: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    dc_name_patterns: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    stock_behaviour_min_soh: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=1, server_default="1")
