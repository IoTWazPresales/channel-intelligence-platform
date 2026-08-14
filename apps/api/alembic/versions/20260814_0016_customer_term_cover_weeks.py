"""Unit 15A — per-customer target cover weeks on commercial_customer_term.

Revision ID: 20260814_0016
Revises: 20260814_0015
Create Date: 2026-08-14

Nullable weeks of cover on the existing customer commercial-term row (D-045).
No new table. Tenant default remains channel_ops_config WOC threshold.

Do not alembic upgrade on cip without Warren approval.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260814_0016"
down_revision: Union[str, Sequence[str], None] = "20260814_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _grant_cip() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON commercial_customer_term TO cip';
              END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "commercial_customer_term" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("commercial_customer_term")}
    if "target_cover_weeks" not in cols:
        op.add_column(
            "commercial_customer_term",
            sa.Column("target_cover_weeks", sa.Numeric(8, 4), nullable=True),
        )
    _grant_cip()


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "commercial_customer_term" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("commercial_customer_term")}
    if "target_cover_weeks" in cols:
        op.drop_column("commercial_customer_term", "target_cover_weeks")
