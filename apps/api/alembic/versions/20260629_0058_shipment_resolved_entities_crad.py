"""shipment_evidence_line + fact_inbound_shipment resolved_* columns and crad_date.

Revision ID: 20260629_0058
Revises: 20260628_0057
Create Date: 2026-06-29

Unit 1 PO↔lineup alignment: alias-collapsed entity FKs plus typed CRAD date.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260629_0058"
down_revision: Union[str, Sequence[str], None] = "20260628_0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("shipment_evidence_line", "fact_inbound_shipment"):
        op.add_column(table, sa.Column("resolved_customer_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("resolved_distributor_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("crad_date", sa.Date(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_resolved_customer_id",
            table,
            "dim_customer",
            ["resolved_customer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            f"fk_{table}_resolved_distributor_id",
            table,
            "dim_distributor",
            ["resolved_distributor_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_resolved_customer_id", table, ["resolved_customer_id"])
        op.create_index(f"ix_{table}_resolved_distributor_id", table, ["resolved_distributor_id"])


def downgrade() -> None:
    for table in ("fact_inbound_shipment", "shipment_evidence_line"):
        op.drop_index(f"ix_{table}_resolved_distributor_id", table_name=table)
        op.drop_index(f"ix_{table}_resolved_customer_id", table_name=table)
        op.drop_constraint(f"fk_{table}_resolved_distributor_id", table, type_="foreignkey")
        op.drop_constraint(f"fk_{table}_resolved_customer_id", table, type_="foreignkey")
        op.drop_column(table, "crad_date")
        op.drop_column(table, "resolved_distributor_id")
        op.drop_column(table, "resolved_customer_id")
