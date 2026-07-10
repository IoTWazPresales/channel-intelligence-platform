"""Per-tenant customer code mint settings (BACKLOG-061-U2b)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CustomerCodeMintSetting(Base):
    """Configurable mint convention per tenant. One seeded row for this install."""

    __tablename__ = "customer_code_mint_setting"

    tenant_id: Mapped[str] = mapped_column(Text, primary_key=True)
    pattern_template: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    separator: Mapped[str] = mapped_column(Text, nullable=False, default="-")
    pad_width: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_mode: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    next_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
