"""commercial_lineup_case.business_unit — first-class BU for supersession key (Spec C Step A).

Revision ID: 20260701_0064
Revises: 20260630_0063
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260701_0064"
down_revision: Union[str, Sequence[str], None] = "20260630_0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commercial_lineup_case",
        sa.Column("business_unit", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commercial_lineup_case", "business_unit")
