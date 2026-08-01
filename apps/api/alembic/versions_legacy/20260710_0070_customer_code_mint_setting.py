"""BACKLOG-061-U2b — customer_code_mint_setting (AUTHOR ONLY — do not apply to cip without Warren).

Revision ID: 20260710_0070
Revises: 20260709_0069

Candidate A seed: CUST-{SEQ:06d}, next_seq=1 (bump allocator handles collisions).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0070"
down_revision: Union[str, Sequence[str], None] = "20260709_0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_code_mint_setting",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("pattern_template", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("separator", sa.Text(), nullable=False, server_default="-"),
        sa.Column("pad_width", sa.Integer(), nullable=False),
        sa.Column("segment_mode", sa.Text(), nullable=False, server_default="none"),
        sa.Column("next_seq", sa.BigInteger(), nullable=False),
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
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO customer_code_mint_setting (
                tenant_id, pattern_template, prefix, separator,
                pad_width, segment_mode, next_seq
            ) VALUES (
                'default', '{PREFIX}{SEP}{SEQ}', 'CUST', '-',
                6, 'none', 1
            )
            """
        )
    )
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON customer_code_mint_setting TO cip"
        )
    )


def downgrade() -> None:
    op.drop_table("customer_code_mint_setting")
