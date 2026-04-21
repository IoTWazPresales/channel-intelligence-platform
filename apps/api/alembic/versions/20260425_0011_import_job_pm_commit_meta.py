"""Product Master async commit tracking on import_job.

Revision ID: 20260425_0011
Revises: 20260424_0010
Create Date: 2026-04-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260425_0011"
down_revision: Union[str, Sequence[str], None] = "20260424_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "import_job",
        sa.Column("pm_commit_meta", JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_job", "pm_commit_meta")
