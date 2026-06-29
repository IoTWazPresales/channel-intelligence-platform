"""commercial_lineup_po_auto_link_dismiss — steward dismissals for auto-link proposals.

Revision ID: 20260629_0059
Revises: 20260629_0058
Create Date: 2026-06-29

Persists dismissed PO↔lineup auto-link proposals (Unit 4) so they do not reappear on review.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260629_0059"
down_revision: Union[str, Sequence[str], None] = "20260629_0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commercial_lineup_po_auto_link_dismiss",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proposal_key", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["commercial_lineup_case.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_order.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_key", name="uq_po_auto_link_dismiss_proposal_key"),
    )
    op.create_index(
        "ix_po_auto_link_dismiss_case_id",
        "commercial_lineup_po_auto_link_dismiss",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_po_auto_link_dismiss_purchase_order_id",
        "commercial_lineup_po_auto_link_dismiss",
        ["purchase_order_id"],
        unique=False,
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON commercial_lineup_po_auto_link_dismiss TO cip"
    )
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE commercial_lineup_po_auto_link_dismiss_id_seq TO cip"
    )


def downgrade() -> None:
    op.drop_index("ix_po_auto_link_dismiss_purchase_order_id", table_name="commercial_lineup_po_auto_link_dismiss")
    op.drop_index("ix_po_auto_link_dismiss_case_id", table_name="commercial_lineup_po_auto_link_dismiss")
    op.drop_table("commercial_lineup_po_auto_link_dismiss")
