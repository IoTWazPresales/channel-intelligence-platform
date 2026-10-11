"""Who may see or edit each product line, and which axis column sets use."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserProductLineAccess(Base):
    __tablename__ = "user_product_line_access"
    __table_args__ = (
        UniqueConstraint("user_id", "product_line", name="uq_user_product_line_access"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_line: Mapped[str] = mapped_column(Text, nullable=False)
    can_edit: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class TenantColumnGrain(Base):
    """Axis for column-set overlays. This business uses product_line."""

    __tablename__ = "tenant_column_grain"

    tenant_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    grain: Mapped[str] = mapped_column(Text, nullable=False, server_default="product_line")
