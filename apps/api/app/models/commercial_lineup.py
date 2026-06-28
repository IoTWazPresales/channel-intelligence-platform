from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

COMMERCIAL_LINEUP_STATUSES = {
    "draft_imported",
    "validated",
    "pending_review",
    "accepted",
    "po_pending",
    "po_issued",
    "in_fulfillment",
    "received_closed",
    "cancelled",
}


class CommercialLineupCase(Base, TimestampMixin):
    __tablename__ = "commercial_lineup_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int | None] = mapped_column(ForeignKey("import_job.id"), nullable=True, index=True)
    commercial_plan_id: Mapped[int | None] = mapped_column(ForeignKey("commercial_plan.id"), nullable=True, index=True)
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    import_intent: Mapped[str] = mapped_column(String(64), nullable=False, default="current_working_lineup")
    source_context: Mapped[str] = mapped_column(String(64), nullable=False, default="commercial_planner")
    commercial_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft_imported")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_line: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inferred_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class CommercialLineupLine(Base, TimestampMixin):
    __tablename__ = "commercial_lineup_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_lineup_case.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True, index=True)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True, index=True)
    customer_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sku_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    part_number_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_raw: Mapped[str | None] = mapped_column(String(512), nullable=True)
    base_unit_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quantity_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    month_split_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    msrp_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    promo_price_evidence_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    dap_evidence_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    rebate_pct_evidence: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    distributor_margin_pct_evidence: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    vat_pct_evidence: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    diagnostic_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw_row_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    row_status: Mapped[str] = mapped_column(String(32), nullable=False, default="imported")
    mapping_confidence: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    customer_feedback: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pricing_chain_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    calc_dap_cost_currency: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    calc_profit_total: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)


class CommercialLineupCasePo(Base, TimestampMixin):
    """Join: confirmed lineup case <-> purchase order (many-to-many).

    One lineup can issue many POs; one PO can cover many lineups (split delivery / amendments).
    Unique (case_id, purchase_order_id) keeps Confirm-with-PO idempotent. PO is shared shipment
    evidence, so only case_id cascades on delete.
    """

    __tablename__ = "commercial_lineup_case_po"
    __table_args__ = (
        UniqueConstraint("case_id", "purchase_order_id", name="uq_case_po_case_purchase_order"),
        Index("ix_clcp_case_id", "case_id"),
        Index("ix_clcp_purchase_order_id", "purchase_order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("commercial_lineup_case.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
