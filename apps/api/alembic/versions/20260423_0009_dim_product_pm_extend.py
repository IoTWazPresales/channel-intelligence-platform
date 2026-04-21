"""Extend dim_product for Product Master identity and commercial fields.

Revision ID: 20260423_0009
Revises: 20260422_0008
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260423_0009"
down_revision: Union[str, Sequence[str], None] = "20260422_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("dim_product", "sku", existing_type=sa.String(length=64), type_=sa.String(length=128), existing_nullable=False)

    op.add_column("dim_product", sa.Column("part_number", sa.String(length=128), nullable=True))
    op.add_column("dim_product", sa.Column("sales_model_name", sa.String(length=512), nullable=True))
    op.add_column("dim_product", sa.Column("model_name", sa.String(length=512), nullable=True))
    op.add_column("dim_product", sa.Column("marketing_name", sa.String(length=512), nullable=True))
    op.add_column("dim_product", sa.Column("series_name", sa.String(length=256), nullable=True))
    op.add_column("dim_product", sa.Column("product_line", sa.String(length=256), nullable=True))
    op.add_column("dim_product", sa.Column("ean", sa.String(length=32), nullable=True))
    op.add_column("dim_product", sa.Column("upc", sa.String(length=32), nullable=True))
    op.add_column("dim_product", sa.Column("business_unit", sa.String(length=128), nullable=True))
    op.add_column("dim_product", sa.Column("lifecycle_status", sa.String(length=64), nullable=True))
    op.add_column("dim_product", sa.Column("country_code", sa.String(length=8), nullable=True))

    op.create_index("ix_dim_product_part_number", "dim_product", ["part_number"], unique=True)

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE dim_product SET part_number = sku WHERE part_number IS NULL"))


def downgrade() -> None:
    op.drop_index("ix_dim_product_part_number", table_name="dim_product")

    for col in (
        "country_code",
        "lifecycle_status",
        "business_unit",
        "upc",
        "ean",
        "product_line",
        "series_name",
        "marketing_name",
        "model_name",
        "sales_model_name",
        "part_number",
    ):
        op.drop_column("dim_product", col)

    op.alter_column("dim_product", "sku", existing_type=sa.String(length=128), type_=sa.String(length=64), existing_nullable=False)
