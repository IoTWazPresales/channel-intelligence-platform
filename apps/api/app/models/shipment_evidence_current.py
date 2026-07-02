"""Read model: latest observation per line_identity_key (``shipment_evidence_current`` view)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShipmentEvidenceCurrent(Base):
    """Mapped to ``shipment_evidence_current`` (view — read-only)."""

    __tablename__ = "shipment_evidence_current"
    __table_args__ = {"info": {"is_view": True}}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_identity_key: Mapped[str] = mapped_column(String(256), nullable=False)
    import_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)
    source_row_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source_sheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    line_state: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_source_row: Mapped[dict] = mapped_column(JSONB, nullable=False)

    operating_unit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bill_to_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ship_to_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)

    order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customer_po: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_line: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivery_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_line: Mapped[str | None] = mapped_column(String(64), nullable=True)

    item_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sales_model_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    customer_item: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ean_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    upc_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mpor_item_no: Mapped[str | None] = mapped_column(String(128), nullable=True)

    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    ship_confirm_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    schedule_ship_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    promise_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exwork_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    erd_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    est_pod_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pod_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    product_resolution_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    product_resolution_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    distributor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distributor_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    distributor_resolution_token: Mapped[str | None] = mapped_column(String(512), nullable=True)

    customer_dealer_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_resolution_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    resolved_customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_distributor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crad_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
