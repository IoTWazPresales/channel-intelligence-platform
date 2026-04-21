"""Product Master: persisted headers, mapping decisions, staged metadata, validation flag.

Revision ID: 20260420_0006
Revises: 20260419_0005
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260420_0006"
down_revision: Union[str, Sequence[str], None] = "20260419_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_job",
        sa.Column("file_headers", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "import_job",
        sa.Column("mapping_decisions", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "import_job",
        sa.Column("staged_metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "import_job",
        sa.Column("validation_passed", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_job", "validation_passed")
    op.drop_column("import_job", "staged_metadata")
    op.drop_column("import_job", "mapping_decisions")
    op.drop_column("import_job", "file_headers")
