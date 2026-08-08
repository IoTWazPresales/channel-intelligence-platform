"""Add distributor_attribution_status on commercial_lineup_line (Unit 6f / D-040).

Revision ID: 20260807_0010
Revises: 20260802_0009
Create Date: 2026-08-07

First-class propose→confirm status for lineup distributor attribution.
Values: token_proposed | steward_set | shipment_confirmed | conflict (nullable).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260807_0010"
down_revision: Union[str, Sequence[str], None] = "20260802_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COL = "distributor_attribution_status"
_TABLE = "commercial_lineup_line"


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    if _COL not in cols:
        op.add_column(
            _TABLE,
            sa.Column(_COL, sa.String(length=32), nullable=True),
        )
        op.create_index(
            "ix_commercial_lineup_line_dist_attr_status",
            _TABLE,
            [_COL],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(_TABLE)}
    if _COL in cols:
        op.drop_index("ix_commercial_lineup_line_dist_attr_status", table_name=_TABLE)
        op.drop_column(_TABLE, _COL)
