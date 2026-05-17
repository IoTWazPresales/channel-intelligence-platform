"""Channel Intelligence Phase 1: customer sell-out, store, retailer listing, promotion product models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DimStore(Base, TimestampMixin):
    """Brick-and-mortar store master for a customer/retailer."""

    __tablename__ = "dim_store"
    __table_args__ = (
        UniqueConstraint("customer_id", "store_code", name="uq_dim_store_customer_store_code"),
        Index("ix_dim_store_customer_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    store_code: Mapped[str] = mapped_column(String(64), nullable=False)
    store_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("dim_region.id"), nullable=True)
    store_type: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CustomerProductAlias(Base, TimestampMixin):
    """Maps a retailer article code to dim_product."""

    __tablename__ = "customer_product_alias"
    __table_args__ = (
        UniqueConstraint("customer_id", "normalized_code", name="uq_customer_product_alias_customer_normalized"),
        Index("ix_customer_product_alias_customer_id", "customer_id"),
        Index("ix_customer_product_alias_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    source_article_code: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(512), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )


class FactCustomerSales(Base, TimestampMixin):
    """Customer sell-out fact table (retailer POS data)."""

    __tablename__ = "fact_customer_sales"
    __table_args__ = (
        Index("ix_fact_customer_sales_customer_id", "customer_id"),
        Index("ix_fact_customer_sales_product_id", "product_id"),
        Index("ix_fact_customer_sales_import_job_id", "import_job_id"),
        Index("ix_fact_customer_sales_report_period", "report_year", "report_week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("dim_store.id"), nullable=True)
    import_job_id: Mapped[int | None] = mapped_column(ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True)

    report_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    quantity_sold: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity_returned: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    selling_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    channel_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reported_soh: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    source_article_code: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_store_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_resolution_status: Mapped[str] = mapped_column(String(64), default="no_match", nullable=False)
    store_resolution_status: Mapped[str] = mapped_column(String(64), default="no_match", nullable=False)
    raw_source_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class DimRetailerListing(Base, TimestampMixin):
    """Maps a product to a retailer product page / listing URL."""

    __tablename__ = "dim_retailer_listing"
    __table_args__ = (
        UniqueConstraint("product_id", "customer_id", "listing_url", name="uq_retailer_listing_product_customer_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    listing_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    retailer_sku: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expected_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    listing_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_price_seen: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    last_availability_seen: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactPromotionProduct(Base, TimestampMixin):
    """Products participating in a promotion (junction with optional distributor/customer scope)."""

    __tablename__ = "fact_promotion_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("dim_promotion.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    expected_uplift_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    target_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
