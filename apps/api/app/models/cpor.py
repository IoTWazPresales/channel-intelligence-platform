"""CPOR v1 case / line / event / claim-evidence models (spec §3).

Lifecycle: soft everything — no hard deletes. Supersession via superseded_by_case_id.
Approval field shape mirrors PromoPlanExport (fields only; workflow in later units).
Computed waterfall columns are nullable until U2 server recompute.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class CporCase(Base, TimestampMixin):
    __tablename__ = "cpor_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    case_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default", index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    promotion_type: Mapped[str] = mapped_column(String(128), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    roe_snapshot: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False, default="ZAR")
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="reseller")
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="native", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Approval / version fields — shape matches PromoPlanExport (no workflow logic in U1)
    export_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workflow_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    last_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Q-001 / BACKLOG-095 — money ceiling exceeded → must reapprove before approve/export
    needs_reapproval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    superseded_by_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cpor_case.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    lines: Mapped[list["CporCaseLine"]] = relationship("CporCaseLine", back_populates="case")
    events: Mapped[list["CporCaseEvent"]] = relationship("CporCaseEvent", back_populates="case")


class CporCaseLine(Base, TimestampMixin):
    __tablename__ = "cpor_case_line"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "product_id",
            "distributor_id",
            "pod_quarter",
            name="uq_cpor_case_line_grain",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cpor_case.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False, index=True)
    distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id"), nullable=True, index=True
    )
    pod_quarter: Mapped[str | None] = mapped_column(String(16), nullable=True)

    srp: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    vat_rate: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    dealer_margin_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    margin_source: Mapped[str] = mapped_column(String(32), nullable=False, default="customer_default")

    cost_basis: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    cost_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    estimate_qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    cap_qty: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    soh_snapshot: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)

    # Computed outputs — server-filled in U2; nullable in U1
    dealer_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    support_unit: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_support: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    support_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)

    result_qty: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_result: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_support_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    ttl_result_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    case: Mapped["CporCase"] = relationship("CporCase", back_populates="lines")


class CporCaseEvent(Base):
    """Audit trail for case lifecycle (approval, status, override). No hard deletes."""

    __tablename__ = "cpor_case_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cpor_case.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped["CporCase"] = relationship("CporCase", back_populates="events")


class CporClaimEvidenceLine(Base, TimestampMixin):
    """Settlement claim import line — source_key upsert; raw_source_row always preserved."""

    __tablename__ = "cpor_claim_evidence_line"
    __table_args__ = (UniqueConstraint("source_key", name="uq_cpor_claim_evidence_line_source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cpor_case.id"), nullable=False, index=True)
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True, index=True)
    source_model_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    raw_source_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False)
