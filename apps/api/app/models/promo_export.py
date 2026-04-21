from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PromoPlanExport(Base, TimestampMixin):
    """Versioned CPOR-style promo plan export artifact + approval workflow."""

    __tablename__ = "promo_plan_export"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[int] = mapped_column(ForeignKey("dim_promotion.id"), nullable=False)

    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    export_version: Mapped[int] = mapped_column(Integer, nullable=False)

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    workflow_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    last_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    promotion = relationship("DimPromotion")
    events: Mapped[list["PromoPlanExportEvent"]] = relationship(
        "PromoPlanExportEvent", back_populates="export", cascade="all, delete-orphan"
    )


class PromoPlanExportEvent(Base):
    """Audit trail for export lifecycle (validate, submit, approve, reject, email)."""

    __tablename__ = "promo_plan_export_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_id: Mapped[int] = mapped_column(ForeignKey("promo_plan_export.id", ondelete="CASCADE"), nullable=False)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    export: Mapped["PromoPlanExport"] = relationship("PromoPlanExport", back_populates="events")
