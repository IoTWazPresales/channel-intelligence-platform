"""Append-only budget ledger. Balances are sums of these rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ENTRY_TYPES = frozenset(
    {"reserve", "transfer", "commit", "commit_adjust", "release", "consume", "paid", "cap"}
)


class BudgetLedgerEntry(Base):
    __tablename__ = "budget_ledger_entry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    product_line: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    landed_quarter: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount_local: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    case_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    case_line_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    lineup_item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payment_evidence_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(Text, nullable=True)
    reverses_entry_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
