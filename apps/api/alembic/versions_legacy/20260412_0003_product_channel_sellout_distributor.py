"""Add product primary channel and optional sell-out distributor mapping.

Revision ID: 20260412_0003
Revises: 20260412_0002
Create Date: 2026-04-12

20260412_0001 already reflects the current ORM (``create_all``), which includes
``dim_product.channel_id`` and ``fact_sales_sellout.distributor_id``. This revision
originally added those columns for older databases; defensive checks keep fresh
upgrades from failing with duplicate-column errors.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import fk_exists, get_inspector, has_column

revision: str = "20260412_0003"
down_revision: Union[str, Sequence[str], None] = "20260412_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_column(insp, "dim_product", "channel_id"):
        op.add_column("dim_product", sa.Column("channel_id", sa.Integer(), nullable=True))
    if not fk_exists(insp, "dim_product", "fk_dim_product_channel_id_dim_channel"):
        op.create_foreign_key(
            "fk_dim_product_channel_id_dim_channel",
            "dim_product",
            "dim_channel",
            ["channel_id"],
            ["id"],
        )

    if not has_column(insp, "fact_sales_sellout", "distributor_id"):
        op.add_column("fact_sales_sellout", sa.Column("distributor_id", sa.Integer(), nullable=True))
    if not fk_exists(insp, "fact_sales_sellout", "fk_fact_sales_sellout_distributor_id_dim_distributor"):
        op.create_foreign_key(
            "fk_fact_sales_sellout_distributor_id_dim_distributor",
            "fact_sales_sellout",
            "dim_distributor",
            ["distributor_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if fk_exists(insp, "fact_sales_sellout", "fk_fact_sales_sellout_distributor_id_dim_distributor"):
        op.drop_constraint(
            "fk_fact_sales_sellout_distributor_id_dim_distributor", "fact_sales_sellout", type_="foreignkey"
        )
    if has_column(insp, "fact_sales_sellout", "distributor_id"):
        op.drop_column("fact_sales_sellout", "distributor_id")

    if fk_exists(insp, "dim_product", "fk_dim_product_channel_id_dim_channel"):
        op.drop_constraint("fk_dim_product_channel_id_dim_channel", "dim_product", type_="foreignkey")
    if has_column(insp, "dim_product", "channel_id"):
        op.drop_column("dim_product", "channel_id")
