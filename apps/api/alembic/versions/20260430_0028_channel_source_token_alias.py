"""Governed DSI route-to-market: channel_source_token_alias + Open Channel dim row.

Revision ID: 20260430_0028
Revises: 20260430_0027
Create Date: 2026-05-06

Idempotent: safe if objects already exist from manual DDL.

Uniqueness: no DB-level unique constraint on (normalized_token, source_definition_id, channel_id).
Approved duplicates for the same token+channel+scope dedupe at resolution; same token mapping to
different channel_ids is a conflict surfaced at resolution time. A hard unique index would block
legitimate parallel source-scoped aliases and is deferred until governance rules are finalized.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from _alembic_revision_helpers import get_inspector, has_index, has_table

revision: str = "20260430_0028"
down_revision: Union[str, Sequence[str], None] = "20260430_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "channel_source_token_alias"):
        op.create_table(
            "channel_source_token_alias",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("channel_id", sa.Integer(), nullable=False),
            sa.Column("source_definition_id", sa.Integer(), nullable=True),
            sa.Column("raw_token", sa.String(length=512), nullable=False),
            sa.Column("normalized_token", sa.String(length=512), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="approved"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_from_import_job_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["channel_id"], ["dim_channel.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_definition_id"], ["source_definition.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_from_import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "channel_source_token_alias", "ix_channel_source_token_alias_norm"):
        op.create_index(
            "ix_channel_source_token_alias_norm",
            "channel_source_token_alias",
            ["normalized_token"],
        )

    # Governed catalog concept for DSI open-channel / indirect retail routes (not a customer row).
    op.execute(
        text(
            """
            INSERT INTO dim_channel (code, name, created_at, updated_at)
            SELECT CAST(:code AS VARCHAR(32)), CAST(:name AS VARCHAR(256)), NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM dim_channel c WHERE c.code = CAST(:code AS VARCHAR(32))
            )
            """
        ),
        {"code": "OPEN_CH", "name": "Open Channel"},
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_index(insp, "channel_source_token_alias", "ix_channel_source_token_alias_norm"):
        op.drop_index("ix_channel_source_token_alias_norm", table_name="channel_source_token_alias")
    insp = get_inspector(bind)
    if has_table(insp, "channel_source_token_alias"):
        op.drop_table("channel_source_token_alias")

    # Do not remove dim_channel OPEN_CH — may be referenced by facts/customers.
