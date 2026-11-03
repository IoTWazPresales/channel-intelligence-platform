"""Canonical shipment / order evidence lines (import-derived, audit-preserving)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.shipment_water import ShipmentWaterColumns


class ShipmentEvidenceLine(ShipmentWaterColumns, Base, TimestampMixin):
    """One logical shipment or order line from an OEM / logistics extract.

    D4: the payload columns (``report_type``, ``line_state``, ``raw_source_row``, the item/quantity/date/token
    columns and the voyage fields) are no longer written; the payload is the line's newest
    ``shipment_evidence_observation`` (see ``shipment_evidence_rows``). Rows loaded before D4 keep their old values.
    The line keeps the job scope and the steward state. D5 drops the payload columns.

    ``source_key`` is a stable per-job identifier from the row's business fields (see
    ``shipment_evidence_source_keys``); re-import upserts on ``(import_job_id, source_key)``.
    """

    __tablename__ = "shipment_evidence_line"
    __table_args__ = (
        Index("ix_shipment_evidence_line_import_job", "import_job_id"),
        # The active corpus: lines no later load has superseded (the readers filter on this).
        Index(
            "ix_shipment_evidence_line_active_corpus",
            "import_job_id",
            postgresql_where=text("corpus_superseded_at IS NULL"),
        ),
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
    # Indexed by ix_shipment_evidence_line_import_job above (a second index=True here made a twin).
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False)
    source_sheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    report_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    line_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)

    raw_source_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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

    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True, index=True)
    product_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    product_resolution_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    product_resolution_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True, index=True)
    distributor_resolution_status: Mapped[str] = mapped_column(String(64), nullable=False)
    distributor_resolution_token: Mapped[str | None] = mapped_column(String(512), nullable=True)

    customer_dealer_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_customer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_resolution_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    resolved_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_customer.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id", ondelete="SET NULL"), nullable=True, index=True
    )
    crad_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    corpus_superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
