"""purchase_order_id FK on shipment evidence + fact_inbound_shipment.

Revision ID: 20260628_0054
Revises: 20260628_0053
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0054"
down_revision: Union[str, Sequence[str], None] = "20260628_0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("shipment_evidence_line", "shipment_evidence_observation", "fact_inbound_shipment"):
        op.add_column(table, sa.Column("purchase_order_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_purchase_order_id",
            table,
            "purchase_order",
            ["purchase_order_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_purchase_order_id", table, ["purchase_order_id"], unique=False)


def downgrade() -> None:
    for table in ("fact_inbound_shipment", "shipment_evidence_observation", "shipment_evidence_line"):
        op.drop_index(f"ix_{table}_purchase_order_id", table_name=table)
        op.drop_constraint(f"fk_{table}_purchase_order_id", table, type_="foreignkey")
        op.drop_column(table, "purchase_order_id")
