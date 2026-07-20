"""CPOR historical import models — mapping profile + staging (H1)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CporHistoricalMappingProfile(Base, TimestampMixin):
    """Tenant mapping profile: sheet roles + column map + status/promo value-maps."""

    __tablename__ = "cpor_historical_mapping_profile"
    __table_args__ = (UniqueConstraint("profile_code", name="uq_cpor_historical_mapping_profile_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    header_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sheet_roles_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    column_map_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    value_maps_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportCporHistoricalStagingLine(Base, TimestampMixin):
    """One workbook line before steward resolve / apply (source_key upsert)."""

    __tablename__ = "import_cpor_historical_staging_line"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_import_cpor_historical_staging_source_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(
        ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    case_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    promotion_type_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promotion_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    window_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lifecycle_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pod_quarter: Mapped[str | None] = mapped_column(String(16), nullable=True)
    product_line: Mapped[str | None] = mapped_column(String(64), nullable=True)
    distributor_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    customer_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sales_model_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    resolved_customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    resolved_distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id"), nullable=True
    )
    resolved_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    soh_snapshot: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    estimate_qty: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    result_qty: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    srp: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    vat_rate: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    dealer_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    cost_basis: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    dealer_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    support_unit: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_support: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    roe_snapshot: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    support_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_support_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_result: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_result_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    skip_apply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flags_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_source_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
