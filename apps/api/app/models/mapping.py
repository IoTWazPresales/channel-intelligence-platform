from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProductAlias(Base, TimestampMixin):
    __tablename__ = "product_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    alias_value: Mapped[str] = mapped_column(String(256), nullable=False)
    alias_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)


class EntityMappingQueue(Base, TimestampMixin):
    __tablename__ = "entity_mapping_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    suggested_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="review_required", nullable=False)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("import_job.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
