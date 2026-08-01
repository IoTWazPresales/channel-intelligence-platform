"""shipment_evidence_line + fact_inbound_shipment customer_po column.

Revision ID: 20260628_0052
Revises: 20260626_0051
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0052"
down_revision: Union[str, Sequence[str], None] = "20260626_0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shipment_evidence_line",
        sa.Column("customer_po", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "shipment_evidence_observation",
        sa.Column("customer_po", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("customer_po", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fact_inbound_shipment", "customer_po")
    op.drop_column("shipment_evidence_observation", "customer_po")
    op.drop_column("shipment_evidence_line", "customer_po")
