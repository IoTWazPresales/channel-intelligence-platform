"""Product Master async commit tracking on import_job.

Revision ID: 20260425_0011
Revises: 20260424_0010
Create Date: 2026-04-25

``pm_commit_meta`` may already exist on ``import_job`` from 20260412_0001.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from _alembic_revision_helpers import get_inspector, has_column

revision: str = "20260425_0011"
down_revision: Union[str, Sequence[str], None] = "20260424_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if not has_column(insp, "import_job", "pm_commit_meta"):
        op.add_column(
            "import_job",
            sa.Column("pm_commit_meta", JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if has_column(insp, "import_job", "pm_commit_meta"):
        op.drop_column("import_job", "pm_commit_meta")
