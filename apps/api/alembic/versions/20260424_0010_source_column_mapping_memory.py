"""Source-scoped Product Master column mapping memory (learned from confirmed saves).

Revision ID: 20260424_0010
Revises: 20260423_0009
Create Date: 2026-04-24

``column_mapping_memory`` may already exist on ``source_definition`` from 20260412_0001.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from _alembic_revision_helpers import get_inspector, has_column

revision: str = "20260424_0010"
down_revision: Union[str, Sequence[str], None] = "20260423_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if not has_column(insp, "source_definition", "column_mapping_memory"):
        op.add_column(
            "source_definition",
            sa.Column("column_mapping_memory", JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if has_column(insp, "source_definition", "column_mapping_memory"):
        op.drop_column("source_definition", "column_mapping_memory")
