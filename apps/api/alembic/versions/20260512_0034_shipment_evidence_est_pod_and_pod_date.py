"""Add est_pod_date and pod_date to shipment_evidence_line.

Estimated Proof of Delivery (expected delivery) and actual Proof of Delivery
(confirmed delivery), nullable until known.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260512_0034"
down_revision: str | None = "20260510_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipment_evidence_line",
        sa.Column("est_pod_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "shipment_evidence_line",
        sa.Column("pod_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shipment_evidence_line", "pod_date")
    op.drop_column("shipment_evidence_line", "est_pod_date")
