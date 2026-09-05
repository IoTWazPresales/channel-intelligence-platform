"""Daily FX quotes stored for case suggestion and historical backfill.

Quote pair USDZAR means ZAR per 1 USD — same orientation as cpor_case.roe_snapshot.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FxDailyRate(Base):
    __tablename__ = "fx_daily_rate"
    __table_args__ = (
        UniqueConstraint("rate_date", "quote_pair", name="uq_fx_daily_rate_date_quote"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quote_pair: Mapped[str] = mapped_column(String(16), nullable=False, default="USDZAR")
    rate: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
