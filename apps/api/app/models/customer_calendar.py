"""Customer campaign / pillar calendars (final wave d).

A customer's own marketing calendar, uploaded through a tenant mapping profile, so our CPOR
promotion windows can be shown beside it and clashes flagged. Both tables are tenant data
(``tenant_id`` and forced row security). Nothing here is specific to a
customer, retailer or site: the customer is a ``dim_customer`` id, the kind is campaign | pillar |
other, and the column mapping is a profile row.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomerCalendarMappingProfile(Base, TimestampMixin):
    """Tenant mapping profile: header row, header aliases per field, kind value map."""

    __tablename__ = "customer_calendar_mapping_profile"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "profile_code", name="uq_customer_calendar_profile_tenant_code"
        ),
        CheckConstraint(
            "header_row_index >= 1", name="ck_customer_calendar_mapping_profile_header_row"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="default", server_default="default", index=True
    )
    profile_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    header_row_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    sheet_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    column_map_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    value_maps_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)


class CustomerCalendarEvent(Base, TimestampMixin):
    """One campaign / pillar / other event on a customer's own calendar."""

    __tablename__ = "customer_calendar_event"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_customer_calendar_event_dates"),
        CheckConstraint(
            "kind IN ('campaign', 'pillar', 'other')", name="ck_customer_calendar_event_kind"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, nullable=False, default="default", server_default="default", index=True
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("dim_customer.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="other", server_default="other"
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    # An upload replaces its own earlier events per customer: (tenant, upload_id, customer_id).
    upload_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("customer_calendar_mapping_profile.id", ondelete="SET NULL"), nullable=True
    )
    raw_source_row: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
