from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HistoricalLineupImportHeader(Base, TimestampMixin):
    __tablename__ = "historical_lineup_import_header"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_job.id"), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_definition.id"), nullable=False, index=True)

    workbook_name: Mapped[str] = mapped_column(String(512), nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(256), nullable=False)
    pm_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)

    period_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True, index=True)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True, index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channel.id"), nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class HistoricalLineupImportLine(Base, TimestampMixin):
    __tablename__ = "historical_lineup_import_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    header_id: Mapped[int] = mapped_column(
        ForeignKey("historical_lineup_import_header.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True, index=True)
    sku_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    part_number_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    base_unit_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)

    msrp_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    promo_price_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    month_split_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    dap_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    actual_dap_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    disti_cost_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    disti_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    rebate_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    dealer_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    vat_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)

    customer_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    row_status: Mapped[str] = mapped_column(String(32), nullable=False, default="accepted")
    mapping_confidence: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    diagnostic_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_row_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
