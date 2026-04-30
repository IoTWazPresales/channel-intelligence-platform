from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CommercialPlan(Base, TimestampMixin):
    __tablename__ = "commercial_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CommercialCustomerTerm(Base, TimestampMixin):
    __tablename__ = "commercial_customer_term"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False, unique=True)
    customer_margin_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.12)
    customer_rebate_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.03)


class CommercialDistributorTerm(Base, TimestampMixin):
    __tablename__ = "commercial_distributor_term"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False, unique=True)
    distributor_margin_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.08)


class CommercialSkuAssumption(Base, TimestampMixin):
    __tablename__ = "commercial_sku_assumption"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False, unique=True)
    controlled_cost_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    controlled_cost_currency_code: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    vat_rate_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.15)
    fx_plan_currency_per_cost_currency: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=1.0)
    reserve_total_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.10)
    promo_reserve_split_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.50)


class CommercialPlanLine(Base, TimestampMixin):
    __tablename__ = "commercial_plan_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    commercial_plan_id: Mapped[int] = mapped_column(ForeignKey("commercial_plan.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id"), nullable=False)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("dim_product.id"), nullable=False)
    target_units: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    target_srp_local: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    promo_srp_local: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    promo_mix_pct: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False, default=0.50)
    launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    promo_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Manual overrides (all optional and explicit)
    override_customer_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    override_customer_rebate_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    override_distributor_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    override_controlled_cost_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    override_controlled_cost_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    override_vat_rate_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    override_fx_plan_currency_per_cost_currency: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    override_reserve_total_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    override_promo_reserve_split_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)

    # Persisted deterministic economics outputs (amounts in economics_calc_currency_code)
    economics_calc_currency_code: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    calc_oem_sell_in_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    calc_distributor_net_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    calc_campaign_support_reserve_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    calc_non_campaign_reserve_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    calc_internal_gp_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    calc_customer_margin_input_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    calc_distributor_margin_input_pct: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    calc_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    calc_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
