"""Staging lines for customer sell-through imports."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ImportCustomerSellthroughStagingLine(Base, TimestampMixin):
    """One source row before resolution / fact apply."""

    __tablename__ = "import_customer_sellthrough_staging_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(
        ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_customer_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_location_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_product_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # N-0111 (Warren 2026-10-19): each product identifier the file carried, stored apart.
    # ``raw_product_token`` is the older single column that may hold any identifier.
    raw_part_number_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_barcode_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_sales_model_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # How the product was found: the Product Master field that matched (part_number, sku, ean, upc,
    # ean_upc, sales_model_name, ...), customer_alias, any_identifier (older layout), steward, or
    # identifier_conflict (the identifiers pointed at different products; not loaded).
    product_match_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Per-identifier outcomes behind the tier (slot, token, status, tier, product ids).
    product_identifier_check: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_period_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    resolved_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_location.id"), nullable=True
    )
    resolved_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    period_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    units_sold: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    raw_mtd_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_mtd_estimate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit_sell_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_mac: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    reported_soh: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    # N-0110: day / week / month as the file states it. A week keeps its number and year;
    # week_start_date is set only when the customer's week calendar is known.
    period_grain: Mapped[str | None] = mapped_column(String(8), nullable=True)
    period_week: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    period_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    week_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Stored apart from on-hand: never added into it.
    in_transit_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    on_order_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    site_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    vat_basis: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_article_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    listing_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    listing_marketplace: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    apply_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fact_sellthrough_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("fact_customer_sellthrough.id", ondelete="SET NULL"), nullable=True
    )
