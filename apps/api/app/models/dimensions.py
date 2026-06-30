from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DimRegion(Base, TimestampMixin):
    __tablename__ = "dim_region"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)


class DimChannel(Base, TimestampMixin):
    __tablename__ = "dim_channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)


class DimDistributor(Base, TimestampMixin):
    __tablename__ = "dim_distributor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    distributor_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    merged_into_distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    merge_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_into: Mapped["DimDistributor | None"] = relationship(
        remote_side="DimDistributor.id",
        foreign_keys=[merged_into_distributor_id],
    )


class DistributorLocation(Base, TimestampMixin):
    __tablename__ = "distributor_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False, index=True)
    location_code: Mapped[str] = mapped_column(String(64), nullable=False)
    location_name: Mapped[str] = mapped_column(String(256), nullable=False)
    location_type: Mapped[str] = mapped_column(String(32), nullable=False, default="branch")
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    address_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    distributor: Mapped["DimDistributor"] = relationship()


class DistributorContact(Base, TimestampMixin):
    __tablename__ = "distributor_contact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False, index=True)
    contact_name: Mapped[str] = mapped_column(String(256), nullable=False)
    contact_role: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    distributor: Mapped["DimDistributor"] = relationship()


class DimCustomer(Base, TimestampMixin):
    __tablename__ = "dim_customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    customer_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    partner_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_owner_internal: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("dim_region.id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)
    preferred_distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id"), nullable=True
    )
    merged_into_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_customer.id", ondelete="SET NULL"), nullable=True, index=False
    )

    region: Mapped["DimRegion | None"] = relationship()
    merged_into_customer: Mapped["DimCustomer | None"] = relationship(
        foreign_keys=[merged_into_customer_id],
        remote_side="DimCustomer.id",
    )
    channel: Mapped["DimChannel | None"] = relationship()
    preferred_distributor: Mapped["DimDistributor | None"] = relationship()


class CustomerLocation(Base, TimestampMixin):
    __tablename__ = "customer_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    location_code: Mapped[str] = mapped_column(String(64), nullable=False)
    location_name: Mapped[str] = mapped_column(String(256), nullable=False)
    location_type: Mapped[str] = mapped_column(String(32), nullable=False, default="store")
    region_id: Mapped[int | None] = mapped_column(ForeignKey("dim_region.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    customer: Mapped["DimCustomer"] = relationship()
    region: Mapped["DimRegion | None"] = relationship()


class CustomerContact(Base, TimestampMixin):
    __tablename__ = "customer_contact"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    contact_name: Mapped[str] = mapped_column(String(256), nullable=False)
    contact_role: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    customer: Mapped["DimCustomer"] = relationship()


class DimProduct(Base, TimestampMixin):
    __tablename__ = "dim_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    part_number: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str | None] = mapped_column(String(256), nullable=True)
    form_factor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    specs_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    price_band: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sales_model_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    marketing_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    series_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    product_line: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ean: Mapped[str | None] = mapped_column(String(32), nullable=True)
    upc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_unit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lifecycle_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retired_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DimDate(Base):
    """Calendar dimension (optional grain for analytics)."""

    __tablename__ = "dim_date"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    calendar_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)


class DimSource(Base, TimestampMixin):
    __tablename__ = "dim_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)


class DimPromotion(Base, TimestampMixin):
    __tablename__ = "dim_promotion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)


class DimCompetitorBrand(Base, TimestampMixin):
    __tablename__ = "dim_competitor_brand"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)


class DimCompetitorProduct(Base, TimestampMixin):
    __tablename__ = "dim_competitor_product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("dim_competitor_brand.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str | None] = mapped_column(String(256), nullable=True)
    specs_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    brand: Mapped["DimCompetitorBrand"] = relationship()


class DimBudgetOwner(Base, TimestampMixin):
    __tablename__ = "dim_budget_owner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
