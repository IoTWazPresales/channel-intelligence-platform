"""Feed-derived listing tokens for LC-U1 handoff (no customer_listing registry yet)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CstListingSeed(Base, TimestampMixin):
    """Durable capture of marketplace listing IDs seen in CST feeds."""

    __tablename__ = "cst_listing_seed"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "marketplace",
            "external_id",
            name="uq_cst_listing_seed_customer_marketplace_external",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    marketplace: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
