"""DSI region/province: region_source_token_alias (parity with channel_source_token_alias).

Revision ID: 20260507_0029
Revises: 20260430_0028
Create Date: 2026-05-07

Idempotent: safe if objects already exist from manual DDL.

Uniqueness: same policy as channel aliases — no hard unique index on (normalized_token,
source_definition_id, region_id); conflicts surface at resolution time.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table

revision: str = "20260507_0029"
down_revision: Union[str, Sequence[str], None] = "20260430_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "region_source_token_alias"):
        op.create_table(
            "region_source_token_alias",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("region_id", sa.Integer(), nullable=False),
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
            sa.ForeignKeyConstraint(["region_id"], ["dim_region.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_definition_id"], ["source_definition.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_from_import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "region_source_token_alias", "ix_region_source_token_alias_norm"):
        op.create_index(
            "ix_region_source_token_alias_norm",
            "region_source_token_alias",
            ["normalized_token"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_index(insp, "region_source_token_alias", "ix_region_source_token_alias_norm"):
        op.drop_index("ix_region_source_token_alias_norm", table_name="region_source_token_alias")
    insp = get_inspector(bind)
    if has_table(insp, "region_source_token_alias"):
        op.drop_table("region_source_token_alias")
