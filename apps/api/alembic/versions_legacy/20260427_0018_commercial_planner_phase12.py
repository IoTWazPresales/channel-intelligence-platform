"""commercial planner phase1+2 foundation

Revision ID: 20260427_0018
Revises: 20260426_0017
Create Date: 2026-04-27 00:18:00

Commercial planner tables may already exist from 20260412_0001 ``create_all``; guarded
DDL keeps a clean-from-empty ``alembic upgrade`` from failing on duplicate tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from _alembic_revision_helpers import get_inspector, has_index, has_table

revision: str = "20260427_0018"
down_revision: str | Sequence[str] | None = "20260426_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "commercial_plan"):
        op.create_table(
            "commercial_plan",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("plan_name", sa.String(length=256), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=True),
            sa.Column("owner", sa.String(length=128), nullable=True),
            sa.Column("environment", sa.String(length=64), nullable=True),
            sa.Column("country_code", sa.String(length=8), nullable=True),
            sa.Column("currency_code", sa.String(length=8), nullable=False, server_default="USD"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )

    insp = get_inspector(bind)
    if not has_table(insp, "commercial_customer_term"):
        op.create_table(
            "commercial_customer_term",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("dim_customer.id"), nullable=False),
            sa.Column("customer_margin_pct", sa.Numeric(8, 4), nullable=False, server_default="0.12"),
            sa.Column("customer_rebate_pct", sa.Numeric(8, 4), nullable=False, server_default="0.03"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("customer_id", name="uq_commercial_customer_term_customer_id"),
        )

    insp = get_inspector(bind)
    if not has_table(insp, "commercial_distributor_term"):
        op.create_table(
            "commercial_distributor_term",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("distributor_id", sa.Integer(), sa.ForeignKey("dim_distributor.id"), nullable=False),
            sa.Column("distributor_margin_pct", sa.Numeric(8, 4), nullable=False, server_default="0.08"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("distributor_id", name="uq_commercial_distributor_term_distributor_id"),
        )

    insp = get_inspector(bind)
    if not has_table(insp, "commercial_sku_assumption"):
        op.create_table(
            "commercial_sku_assumption",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("dim_product.id"), nullable=False),
            sa.Column("landed_cost_usd", sa.Numeric(18, 4), nullable=False),
            sa.Column("vat_rate_pct", sa.Numeric(8, 4), nullable=False, server_default="0.15"),
            sa.Column("fx_rate_to_usd", sa.Numeric(18, 6), nullable=False, server_default="1.0"),
            sa.Column("reserve_total_pct", sa.Numeric(8, 4), nullable=False, server_default="0.10"),
            sa.Column("promo_reserve_split_pct", sa.Numeric(8, 4), nullable=False, server_default="0.50"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("product_id", name="uq_commercial_sku_assumption_product_id"),
        )

    insp = get_inspector(bind)
    if not has_table(insp, "commercial_plan_line"):
        op.create_table(
            "commercial_plan_line",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("commercial_plan_id", sa.Integer(), sa.ForeignKey("commercial_plan.id"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("dim_customer.id"), nullable=False),
            sa.Column("distributor_id", sa.Integer(), sa.ForeignKey("dim_distributor.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("dim_product.id"), nullable=False),
            sa.Column("target_units", sa.Numeric(18, 4), nullable=False),
            sa.Column("target_srp_local", sa.Numeric(18, 4), nullable=False),
            sa.Column("promo_srp_local", sa.Numeric(18, 4), nullable=True),
            sa.Column("promo_mix_pct", sa.Numeric(8, 4), nullable=False, server_default="0.50"),
            sa.Column("launch_date", sa.Date(), nullable=True),
            sa.Column("promo_start_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("override_customer_margin_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("override_customer_rebate_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("override_distributor_margin_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("override_landed_cost_usd", sa.Numeric(18, 4), nullable=True),
            sa.Column("override_vat_rate_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("override_fx_rate_to_usd", sa.Numeric(18, 6), nullable=True),
            sa.Column("override_reserve_total_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("override_promo_reserve_split_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("calc_sell_in_price_usd", sa.Numeric(18, 4), nullable=True),
            sa.Column("calc_buy_price_usd", sa.Numeric(18, 4), nullable=True),
            sa.Column("calc_promo_reserve_usd", sa.Numeric(18, 4), nullable=True),
            sa.Column("calc_non_promo_reserve_usd", sa.Numeric(18, 4), nullable=True),
            sa.Column("calc_internal_gp_usd", sa.Numeric(18, 4), nullable=True),
            sa.Column("calc_customer_gp_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("calc_distributor_gp_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("calc_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("calc_explanation", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "commercial_plan_line", "ix_commercial_plan_line_commercial_plan_id"):
        op.create_index("ix_commercial_plan_line_commercial_plan_id", "commercial_plan_line", ["commercial_plan_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_index(insp, "commercial_plan_line", "ix_commercial_plan_line_commercial_plan_id"):
        op.drop_index("ix_commercial_plan_line_commercial_plan_id", table_name="commercial_plan_line")
    insp = get_inspector(bind)
    if has_table(insp, "commercial_plan_line"):
        op.drop_table("commercial_plan_line")
    insp = get_inspector(bind)
    if has_table(insp, "commercial_sku_assumption"):
        op.drop_table("commercial_sku_assumption")
    insp = get_inspector(bind)
    if has_table(insp, "commercial_distributor_term"):
        op.drop_table("commercial_distributor_term")
    insp = get_inspector(bind)
    if has_table(insp, "commercial_customer_term"):
        op.drop_table("commercial_customer_term")
    insp = get_inspector(bind)
    if has_table(insp, "commercial_plan"):
        op.drop_table("commercial_plan")
