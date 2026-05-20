"""Add import_job.archived_at for hiding completed apply/commit jobs from the default list."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260513_0035"
down_revision: str | None = "20260512_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_job",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_job", "archived_at")
