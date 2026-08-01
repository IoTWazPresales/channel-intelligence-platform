"""Link product_catalog_default source to default_master catalog.

Revision ID: 20260422_0008
Revises: 20260421_0007
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260422_0008"
down_revision: Union[str, Sequence[str], None] = "20260421_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
        UPDATE source_definition sd
        SET product_catalog_id = pc.id
        FROM product_catalog pc
        INNER JOIN business_unit bu ON pc.business_unit_id = bu.id
        WHERE sd.code = 'product_catalog_default'
          AND sd.product_catalog_id IS NULL
          AND bu.code = 'platform'
          AND pc.code = 'default_master'
        """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
        UPDATE source_definition sd
        SET product_catalog_id = NULL
        FROM product_catalog pc
        INNER JOIN business_unit bu ON pc.business_unit_id = bu.id
        WHERE sd.code = 'product_catalog_default'
          AND sd.product_catalog_id = pc.id
          AND bu.code = 'platform'
          AND pc.code = 'default_master'
        """
        )
    )
