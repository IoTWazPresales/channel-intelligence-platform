"""Customer × retailer article number → dim_product (exact-key; steward-confirmed).

Effective-dated eras: half-open [valid_from, valid_to), NULL = ±infinity.
Confirmed/active eras for the same (customer, article) must not overlap
(DB exclusion constraint).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CustomerArticleAlias(Base, TimestampMixin):
    """Exact-key alias for CST article numbers. Never fuzzy; never silent-confirm."""

    __tablename__ = "customer_article_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, index=True)
    article_no_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
