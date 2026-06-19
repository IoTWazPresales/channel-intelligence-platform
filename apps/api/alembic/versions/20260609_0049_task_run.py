"""Background task_run ledger table.

Revision ID: 20260609_0049
Revises: 20260608_0048
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260609_0049"
down_revision: Union[str, Sequence[str], None] = "20260608_0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_run",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("task_name", sa.String(length=128), nullable=False),
        sa.Column("task_class", sa.String(length=64), nullable=False),
        sa.Column("transport", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_run")),
    )
    op.create_index("ix_task_run_entity", "task_run", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_task_run_state", "task_run", ["state"], unique=False)
    op.create_index("ix_task_run_heartbeat_at", "task_run", ["heartbeat_at"], unique=False)
    op.create_index("ix_task_run_task_name", "task_run", ["task_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_task_run_task_name", table_name="task_run")
    op.drop_index("ix_task_run_heartbeat_at", table_name="task_run")
    op.drop_index("ix_task_run_state", table_name="task_run")
    op.drop_index("ix_task_run_entity", table_name="task_run")
    op.drop_table("task_run")
