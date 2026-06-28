"""commercial_lineup_case_po join table (lineup case <-> purchase order, many-to-many).

Revision ID: 20260628_0057
Revises: 20260628_0056
Create Date: 2026-06-28

Links a confirmed lineup case to one or more purchase orders (and a PO to one or more
lineup cases). CASCADE on case_id (deleting a case drops its links); no cascade on
purchase_order_id because a PO is shared shipment evidence. The (case_id, purchase_order_id)
unique constraint makes Confirm-with-PO idempotent (re-confirm = no-op; new PO = append).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0057"
down_revision: Union[str, Sequence[str], None] = "20260628_0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commercial_lineup_case_po",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["commercial_lineup_case.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_order.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "purchase_order_id", name="uq_case_po_case_purchase_order"),
    )
    op.create_index("ix_clcp_case_id", "commercial_lineup_case_po", ["case_id"], unique=False)
    op.create_index(
        "ix_clcp_purchase_order_id", "commercial_lineup_case_po", ["purchase_order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_clcp_purchase_order_id", table_name="commercial_lineup_case_po")
    op.drop_index("ix_clcp_case_id", table_name="commercial_lineup_case_po")
    op.drop_table("commercial_lineup_case_po")
