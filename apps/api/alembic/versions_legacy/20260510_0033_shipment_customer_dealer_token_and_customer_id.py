"""Rename shipment customer raw column to customer_dealer_token; add customer_id FK.

Aligns ORM with DSI naming (``customer_dealer_token``). ``customer_id`` links resolved
lines to ``dim_customer``; steward paths stamp it after alias creation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260510_0033"
down_revision: str | None = "20260509_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE shipment_evidence_line RENAME COLUMN customer_token_raw TO customer_dealer_token")
    )
    op.add_column(
        "shipment_evidence_line",
        sa.Column("customer_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_shipment_evidence_line_customer_id_dim_customer",
        "shipment_evidence_line",
        "dim_customer",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_shipment_evidence_line_customer_id_dim_customer",
        "shipment_evidence_line",
        type_="foreignkey",
    )
    op.drop_column("shipment_evidence_line", "customer_id")
    op.execute(
        sa.text("ALTER TABLE shipment_evidence_line RENAME COLUMN customer_dealer_token TO customer_token_raw")
    )
