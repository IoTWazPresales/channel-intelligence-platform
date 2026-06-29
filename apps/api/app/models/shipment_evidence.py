"""Canonical shipment / order evidence lines (import-derived, audit-preserving)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ShipmentEvidenceLine(Base, TimestampMixin):
    """One logical shipment or order line from an OEM / logistics extract.

    ``line_state`` distinguishes executed shipments vs open-order / pipeline rows.
    ``report_type`` records which extractor produced the row (source audit).
    ``source_key`` is a stable per-job identifier from the row's business fields (see
    ``shipment_evidence_source_keys``); re-import upserts on ``(import_job_id, source_key)``.
    """

    __tablename__ = "shipment_evidence_line"
    __table_args__ = (
        Index("ix_shipment_evidence_line_import_job", "import_job_id"),
        Index("ix_shipment_evidence_line_line_state", "line_state"),
        Index("ix_shipment_evidence_line_report_type", "report_type"),
        Index("ix_shipment_evidence_line_product_status", "product_resolution_status"),
        UniqueConstraint(
            "import_job_id",
            "source_key",
            name="uq_shipment_evidence_line_import_job_source_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(
        ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_sheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    line_state: Mapped[str] = mapped_column(String(32), nullable=False)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)

    raw_source_row: Mapped[dict] = mapped_column(JSONB, nullable=False)

    operating_unit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bill_to_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ship_to_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)

    order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    customer_po: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_order.id", ondelete="SET NULL"), nullable=True, index=True
    )
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

    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    product_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    product_resolution_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    product_resolution_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)
    distributor_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    distributor_resolution_token: Mapped[str | None] = mapped_column(String(512), nullable=True)

    customer_dealer_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id", ondelete="SET NULL"), nullable=True)
    customer_resolution_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    resolved_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_customer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id", ondelete="SET NULL"), nullable=True, index=True
    )
    crad_date: Mapped[date | None] = mapped_column(Date, nullable=True)
