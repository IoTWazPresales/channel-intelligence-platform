"""Distributor inventory DSI: source_key upsert + SOH reconciliation columns.

Revision ID: 20260518_0040
Revises: 20260518_0039

- Add ``source_key`` (``dsi-soh:{distributor}:{product}:{as_of_date}``) with unique constraint.
- Drop ``uq_fact_inventory_distributor_dsi_v1`` (table empty at migration time).
- Reconciliation placeholders: ``calculated_soh``, ``soh_variance``, ``reconciliation_status``,
  ``reconciliation_run_at`` — populated by later reconciliation jobs, not DSI apply.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_column, unique_constraint_exists

revision: str = "20260518_0040"
down_revision: Union[str, Sequence[str], None] = "20260518_0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_column(insp, "fact_inventory_distributor", "source_key"):
        op.add_column(
            "fact_inventory_distributor",
            sa.Column("source_key", sa.String(length=256), nullable=True),
        )

    op.execute(
        sa.text(
            """
            UPDATE fact_inventory_distributor
            SET source_key = 'dsi-soh:'
                || distributor_id::text || ':'
                || product_id::text || ':'
                || as_of_date::text
            WHERE source_key IS NULL
            """
        )
    )

    if unique_constraint_exists(insp, "fact_inventory_distributor", "uq_fact_inventory_distributor_dsi_v1"):
        op.drop_constraint(
            "uq_fact_inventory_distributor_dsi_v1",
            "fact_inventory_distributor",
            type_="unique",
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_inventory_distributor", "uq_fact_inventory_distributor_source_key"):
        op.create_unique_constraint(
            "uq_fact_inventory_distributor_source_key",
            "fact_inventory_distributor",
            ["source_key"],
        )

    op.alter_column(
        "fact_inventory_distributor",
        "source_key",
        existing_type=sa.String(length=256),
        nullable=False,
    )

    for col, col_type in (
        ("calculated_soh", sa.Numeric(18, 4)),
        ("soh_variance", sa.Numeric(18, 4)),
        ("reconciliation_status", sa.String(length=32)),
        ("reconciliation_run_at", sa.DateTime(timezone=True)),
    ):
        insp = get_inspector(bind)
        if not has_column(insp, "fact_inventory_distributor", col):
            op.add_column("fact_inventory_distributor", sa.Column(col, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    for col in ("reconciliation_run_at", "reconciliation_status", "soh_variance", "calculated_soh"):
        if has_column(insp, "fact_inventory_distributor", col):
            op.drop_column("fact_inventory_distributor", col)

    if unique_constraint_exists(insp, "fact_inventory_distributor", "uq_fact_inventory_distributor_source_key"):
        op.drop_constraint(
            "uq_fact_inventory_distributor_source_key",
            "fact_inventory_distributor",
            type_="unique",
        )

    if has_column(insp, "fact_inventory_distributor", "source_key"):
        op.drop_column("fact_inventory_distributor", "source_key")

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_inventory_distributor", "uq_fact_inventory_distributor_dsi_v1"):
        op.create_unique_constraint(
            "uq_fact_inventory_distributor_dsi_v1",
            "fact_inventory_distributor",
            ["distributor_id", "product_id", "as_of_date"],
        )
