from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
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


class DimCustomer(Base, TimestampMixin):
    __tablename__ = "dim_customer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("dim_region.id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)

    region: Mapped["DimRegion | None"] = relationship()
    channel: Mapped["DimChannel | None"] = relationship()


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
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True)

    channel: Mapped["DimChannel | None"] = relationship()


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
