"""commercial_lineup_case.superseded_by_case_id — soft supersession (Spec C Step B).

Revision ID: 20260701_0065
Revises: 20260701_0064
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260701_0065"
down_revision: Union[str, Sequence[str], None] = "20260701_0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commercial_lineup_case",
        sa.Column("superseded_by_case_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_commercial_lineup_case_superseded_by_case_id",
        "commercial_lineup_case",
        "commercial_lineup_case",
        ["superseded_by_case_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_commercial_lineup_case_superseded_by_case_id",
        "commercial_lineup_case",
        ["superseded_by_case_id"],
        unique=False,
        postgresql_where=sa.text("superseded_by_case_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commercial_lineup_case_superseded_by_case_id",
        table_name="commercial_lineup_case",
        postgresql_where=sa.text("superseded_by_case_id IS NOT NULL"),
    )
    op.drop_constraint(
        "fk_commercial_lineup_case_superseded_by_case_id",
        "commercial_lineup_case",
        type_="foreignkey",
    )
    op.drop_column("commercial_lineup_case", "superseded_by_case_id")
