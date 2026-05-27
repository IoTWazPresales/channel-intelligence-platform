from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class FactCustomerVelocity(Base, TimestampMixin):
    """Distributor sell-out velocity per product/customer (one current row per grain)."""

    __tablename__ = "fact_customer_velocity"
    __table_args__ = (
        Index("ix_fact_customer_velocity_dist", "distributor_id"),
        Index(
            "ix_fact_customer_velocity_dist_prod_cust",
            "distributor_id",
            "product_id",
            "customer_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    computed_through_date: Mapped[date] = mapped_column(Date, nullable=False)
    velocity_4wk: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    velocity_13wk: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    velocity_52wk: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    seasonal_index: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    is_promotional_period: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
