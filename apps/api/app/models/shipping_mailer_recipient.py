"""Per-tenant shipping-digest SMTP recipient list (governed, not CIP users)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShippingMailerRecipient(Base):
    """External SMTP To-row. Casing in ``address`` is preserved for send."""

    __tablename__ = "shipping_mailer_recipient"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    added_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_shipping_mailer_recipient_tenant_address_lower",
            "tenant_id",
            func.lower(address),
            unique=True,
        ),
    )
