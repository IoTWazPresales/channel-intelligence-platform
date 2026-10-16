"""Saved column layouts for customer sell-through uploads (N-0111, Warren 2026-10-16).

A layout is the only per-customer configuration of a sell-through upload: which file headers
map to which standard sell-through columns. One layout per customer and header set; a customer
may have several (weekly report, history file, wide-week).
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomerSellthroughLayout(Base, TimestampMixin):
    __tablename__ = "customer_sellthrough_layout"
    __table_args__ = (
        UniqueConstraint("customer_id", "header_signature", name="uq_cst_layout_customer_signature"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Fingerprint of the normalised header set the layout was saved from (see cst_layouts.layout_signature).
    header_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    headers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # File header -> standard sell-through column (customer_sell_through_flat.CANONICAL_FIELDS).
    field_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # How the file is laid out (flat / pivoted / mtd_delta ...); a new layout is flat.
    report_structure_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # upload = saved from the mapping step; migrated_source = carried over from a former source.
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    origin_source_id: Mapped[int | None] = mapped_column(ForeignKey("source_definition.id"), nullable=True)
    origin_import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
    # Soft remove: a hidden layout is not matched or listed; nothing is deleted.
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
