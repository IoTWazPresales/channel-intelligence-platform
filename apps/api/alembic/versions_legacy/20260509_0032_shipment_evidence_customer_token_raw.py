"""Add customer_token_raw and customer_resolution_status to shipment_evidence_line.

``customer_resolution_status`` is steward-owned (excluded from import upsert ``set_``) so
re-import does not clear a resolved channel-partner mapping while ``customer_token_raw`` is refreshed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260509_0032"
down_revision: str | None = "20260508_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipment_evidence_line",
        sa.Column("customer_token_raw", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "shipment_evidence_line",
        sa.Column("customer_resolution_status", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shipment_evidence_line", "customer_resolution_status")
    op.drop_column("shipment_evidence_line", "customer_token_raw")
