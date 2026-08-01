"""DSI V1 natural keys for idempotent sell-out and distributor inventory facts.

Revision ID: 20260430_0025
Revises: 20260430_0024
Create Date: 2026-04-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from _alembic_revision_helpers import get_inspector, unique_constraint_exists

revision: str = "20260430_0025"
down_revision: Union[str, Sequence[str], None] = "20260430_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    # Remove duplicates so a stable natural-key unique constraint can be enforced (keep lowest id per key).
    op.execute(
        """
        DELETE FROM fact_sales_sellout f
        USING fact_sales_sellout f2
        WHERE f.id > f2.id
          AND f.distributor_id IS NOT DISTINCT FROM f2.distributor_id
          AND f.customer_id = f2.customer_id
          AND f.product_id = f2.product_id
          AND f.period_start = f2.period_start
        """
    )
    op.execute(
        """
        DELETE FROM fact_inventory_distributor f
        USING fact_inventory_distributor f2
        WHERE f.id > f2.id
          AND f.distributor_id = f2.distributor_id
          AND f.product_id = f2.product_id
          AND f.as_of_date = f2.as_of_date
        """
    )
    if not unique_constraint_exists(insp, "fact_sales_sellout", "uq_fact_sales_sellout_dsi_v1"):
        op.create_unique_constraint(
            "uq_fact_sales_sellout_dsi_v1",
            "fact_sales_sellout",
            ["distributor_id", "customer_id", "product_id", "period_start"],
        )
    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_inventory_distributor", "uq_fact_inventory_distributor_dsi_v1"):
        op.create_unique_constraint(
            "uq_fact_inventory_distributor_dsi_v1",
            "fact_inventory_distributor",
            ["distributor_id", "product_id", "as_of_date"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if unique_constraint_exists(insp, "fact_inventory_distributor", "uq_fact_inventory_distributor_dsi_v1"):
        op.drop_constraint("uq_fact_inventory_distributor_dsi_v1", "fact_inventory_distributor", type_="unique")
    insp = get_inspector(bind)
    if unique_constraint_exists(insp, "fact_sales_sellout", "uq_fact_sales_sellout_dsi_v1"):
        op.drop_constraint("uq_fact_sales_sellout_dsi_v1", "fact_sales_sellout", type_="unique")
