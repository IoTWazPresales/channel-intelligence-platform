"""Queue for price entries whose SKU is not in the product master.

Revision ID: 20261011_0030
Revises: 20261010_0029
Create Date: 2026-10-11

One row per SKU. Writing a price fact for that SKU removes the row.
This table does not create dim_product.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261011_0030"
down_revision: Union[str, Sequence[str], None] = "20261010_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_unknown_sku (
            id serial PRIMARY KEY,
            sku varchar(64) NOT NULL,
            list_price numeric(18, 4) NOT NULL,
            net_price numeric(18, 4) NOT NULL,
            currency varchar(8) NOT NULL DEFAULT 'USD',
            effective_date date NOT NULL,
            customer_code varchar(64),
            channel_code varchar(32),
            attempt_count integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_pricing_unknown_sku_sku UNIQUE (sku)
        )
        """
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON pricing_unknown_sku TO cip;
        GRANT USAGE, SELECT ON SEQUENCE pricing_unknown_sku_id_seq TO cip;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pricing_unknown_sku")
