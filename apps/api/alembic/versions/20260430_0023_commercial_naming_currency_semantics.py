"""Commercial naming: controlled cost, FX bridge, economics amounts (currency explicit).

Revision ID: 20260430_0023
Revises: 20260429_0022
Create Date: 2026-04-30

Renames misleading *landed* / *_usd* / *gp* columns to match audited semantics.
Backfills currency columns with USD where historical amounts were stored in the USD-shaped path.
Downgrade restores prior column names.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260430_0023"
down_revision: Union[str, Sequence[str], None] = "20260429_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else "postgresql"
    if dialect != "postgresql":
        raise RuntimeError("This migration targets PostgreSQL (RENAME COLUMN).")

    # --- commercial_sku_assumption ---
    op.add_column(
        "commercial_sku_assumption",
        sa.Column("controlled_cost_currency_code", sa.String(length=8), nullable=False, server_default="USD"),
    )
    op.execute(sa.text("ALTER TABLE commercial_sku_assumption RENAME COLUMN landed_cost_usd TO controlled_cost_amount"))
    op.execute(
        sa.text(
            "ALTER TABLE commercial_sku_assumption RENAME COLUMN fx_rate_to_usd TO fx_plan_currency_per_cost_currency"
        )
    )
    op.alter_column("commercial_sku_assumption", "controlled_cost_currency_code", server_default=None)

    # --- commercial_plan_line ---
    op.add_column(
        "commercial_plan_line",
        sa.Column("economics_calc_currency_code", sa.String(length=8), nullable=False, server_default="USD"),
    )
    op.add_column(
        "commercial_plan_line",
        sa.Column("override_controlled_cost_currency_code", sa.String(length=8), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE commercial_plan_line
            SET override_controlled_cost_currency_code = 'USD'
            WHERE override_landed_cost_usd IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN override_landed_cost_usd TO override_controlled_cost_amount")
    )
    op.execute(
        sa.text(
            "ALTER TABLE commercial_plan_line RENAME COLUMN override_fx_rate_to_usd TO override_fx_plan_currency_per_cost_currency"
        )
    )
    op.execute(sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_sell_in_price_usd TO calc_oem_sell_in_amount"))
    op.execute(sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_buy_price_usd TO calc_distributor_net_amount"))
    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_promo_reserve_usd TO calc_campaign_support_reserve_amount")
    )
    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_non_promo_reserve_usd TO calc_non_campaign_reserve_amount")
    )
    op.execute(sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_internal_gp_usd TO calc_internal_gp_amount"))
    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_customer_gp_pct TO calc_customer_margin_input_pct")
    )
    op.execute(
        sa.text(
            "ALTER TABLE commercial_plan_line RENAME COLUMN calc_distributor_gp_pct TO calc_distributor_margin_input_pct"
        )
    )
    op.alter_column("commercial_plan_line", "economics_calc_currency_code", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else "postgresql"
    if dialect != "postgresql":
        raise RuntimeError("This migration targets PostgreSQL.")

    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_distributor_margin_input_pct TO calc_distributor_gp_pct")
    )
    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_customer_margin_input_pct TO calc_customer_gp_pct")
    )
    op.execute(sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_internal_gp_amount TO calc_internal_gp_usd"))
    op.execute(
        sa.text(
            "ALTER TABLE commercial_plan_line RENAME COLUMN calc_non_campaign_reserve_amount TO calc_non_promo_reserve_usd"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE commercial_plan_line RENAME COLUMN calc_campaign_support_reserve_amount TO calc_promo_reserve_usd"
        )
    )
    op.execute(sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_distributor_net_amount TO calc_buy_price_usd"))
    op.execute(sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN calc_oem_sell_in_amount TO calc_sell_in_price_usd"))
    op.execute(
        sa.text(
            "ALTER TABLE commercial_plan_line RENAME COLUMN override_fx_plan_currency_per_cost_currency TO override_fx_rate_to_usd"
        )
    )
    op.execute(
        sa.text("ALTER TABLE commercial_plan_line RENAME COLUMN override_controlled_cost_amount TO override_landed_cost_usd")
    )
    op.drop_column("commercial_plan_line", "override_controlled_cost_currency_code")
    op.drop_column("commercial_plan_line", "economics_calc_currency_code")

    op.execute(
        sa.text(
            "ALTER TABLE commercial_sku_assumption RENAME COLUMN fx_plan_currency_per_cost_currency TO fx_rate_to_usd"
        )
    )
    op.execute(sa.text("ALTER TABLE commercial_sku_assumption RENAME COLUMN controlled_cost_amount TO landed_cost_usd"))
    op.drop_column("commercial_sku_assumption", "controlled_cost_currency_code")
