"""Line-up plan item approval audit events.

Revision ID: 20260418_0004
Revises: 20260412_0003
Create Date: 2026-04-18

``lineup_plan_item_event`` may already exist from 20260412_0001 ``create_all`` once the
ORM included this table; keep revision idempotent for clean-from-empty upgrades.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table

revision: str = "20260418_0004"
down_revision: Union[str, Sequence[str], None] = "20260412_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "lineup_plan_item_event"):
        op.create_table(
            "lineup_plan_item_event",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("lineup_item_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False, server_default="approval_changed"),
            sa.Column("old_approval_status", sa.String(length=32), nullable=True),
            sa.Column("new_approval_status", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("actor", sa.String(length=128), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["lineup_item_id"],
                ["fact_lineup_plan_item.id"],
                name="fk_lineup_plan_item_event_lineup_item_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_index(insp, "lineup_plan_item_event", "ix_lineup_plan_item_event_lineup_item_id"):
        op.create_index(
            "ix_lineup_plan_item_event_lineup_item_id",
            "lineup_plan_item_event",
            ["lineup_item_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_index(insp, "lineup_plan_item_event", "ix_lineup_plan_item_event_lineup_item_id"):
        op.drop_index("ix_lineup_plan_item_event_lineup_item_id", table_name="lineup_plan_item_event")
    if has_table(insp, "lineup_plan_item_event"):
        op.drop_table("lineup_plan_item_event")
