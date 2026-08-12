"""CPOR payment / credit-note evidence — tenant-agnostic settlement truth.

Distinct from case line economics (SRP/qty/support) and from claim-evidence units.
Profiles map tenant workbooks onto these canonical fields; Ken Pending Report is one profile.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CporPaymentMappingProfile(Base, TimestampMixin):
    """Tenant mapping profile: sheet roles + column map + payment-status value maps."""

    __tablename__ = "cpor_payment_mapping_profile"
    __table_args__ = (UniqueConstraint("profile_code", name="uq_cpor_payment_mapping_profile_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    header_row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sheet_roles_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    column_map_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    value_maps_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportCporPaymentStagingLine(Base, TimestampMixin):
    """One payment-evidence row before steward resolve / apply (source_key upsert)."""

    __tablename__ = "import_cpor_payment_staging_line"
    __table_args__ = (
        UniqueConstraint("source_key", name="uq_import_cpor_payment_staging_source_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(
        ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)

    external_case_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    credit_note_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    case_status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    customer_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    distributor_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    promotion_type_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)

    resolved_customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    resolved_distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id"), nullable=True
    )
    linked_case_id: Mapped[int | None] = mapped_column(ForeignKey("cpor_case.id"), nullable=True, index=True)
    create_shell_case: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skip_apply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flags_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_source_row: Mapped[dict] = mapped_column(JSONB, nullable=False)


class CporPaymentEvidence(Base, TimestampMixin):
    """Applied payment / CN evidence. Case status from file stays evidence-only."""

    __tablename__ = "cpor_payment_evidence"
    __table_args__ = (UniqueConstraint("source_key", name="uq_cpor_payment_evidence_source_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default", index=True)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True, index=True
    )

    external_case_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    credit_note_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    case_status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False, default="ZAR")
    customer_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    distributor_token: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True, index=True)
    distributor_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_distributor.id"), nullable=True, index=True
    )
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cpor_case.id"), nullable=True, index=True)

    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_source_row: Mapped[dict] = mapped_column(JSONB, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
