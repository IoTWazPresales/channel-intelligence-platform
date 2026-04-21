"""Source-scoped Product Master column mapping memory (learned from confirmed saves).

Revision ID: 20260424_0010
Revises: 20260423_0009
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260424_0010"
down_revision: Union[str, Sequence[str], None] = "20260423_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "source_definition",
        sa.Column("column_mapping_memory", JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_definition", "column_mapping_memory")
