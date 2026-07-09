"""Customer × retailer article number → dim_product (exact-key; steward-confirmed)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomerArticleAlias(Base, TimestampMixin):
    """Exact-key alias for CST article numbers. Never fuzzy; never silent-confirm."""

    __tablename__ = "customer_article_alias"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "article_no_normalized",
            name="uq_customer_article_alias_customer_article",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    article_no_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
