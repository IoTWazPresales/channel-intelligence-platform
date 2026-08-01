"""Append-only steward decision audit (P2-3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StewardAuditEvent(Base):
    __tablename__ = "steward_audit_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    importer: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_job_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    candidate_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_dim: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
