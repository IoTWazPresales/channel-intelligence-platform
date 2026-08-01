"""P3-6 SQL viewer audit — who ran what."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SqlViewerAudit(Base):
    __tablename__ = "sql_viewer_audit"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'refused', 'error', 'timeout')",
            name="ck_sql_viewer_audit_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
