"""BACKLOG-132 Unit C — report_delivery email channel + send audit columns.

Revision ID: 20260818_0018
Revises: 20260817_0017
Create Date: 2026-08-18

Honest SMTP audit rows use channel='email' with recipient_email and
provider_message_id. Do not alembic upgrade on cip without Warren approval.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260818_0018"
down_revision: Union[str, Sequence[str], None] = "20260817_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "report_delivery" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("report_delivery")}
    op.execute(sa.text("ALTER TABLE report_delivery DROP CONSTRAINT IF EXISTS ck_report_delivery_channel"))
    op.execute(
        sa.text(
            "ALTER TABLE report_delivery DROP CONSTRAINT IF EXISTS ck_report_delivery_ck_report_delivery_channel"
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE report_delivery
            ADD CONSTRAINT ck_report_delivery_ck_report_delivery_channel
            CHECK (channel IN ('inbox', 'email_stub', 'email'))
            """
        )
    )
    if "recipient_email" not in cols:
        op.add_column("report_delivery", sa.Column("recipient_email", sa.Text(), nullable=True))
    if "provider_message_id" not in cols:
        op.add_column("report_delivery", sa.Column("provider_message_id", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "report_delivery" not in tables:
        return
    remaining = bind.execute(sa.text("SELECT count(*) FROM report_delivery WHERE channel = 'email'")).scalar()
    if remaining:
        raise RuntimeError(
            f"cannot downgrade 20260818_0018: {remaining} report_delivery rows still have channel='email'"
        )
    cols = {c["name"] for c in insp.get_columns("report_delivery")}
    if "provider_message_id" in cols:
        op.drop_column("report_delivery", "provider_message_id")
    if "recipient_email" in cols:
        op.drop_column("report_delivery", "recipient_email")
    op.execute(sa.text("ALTER TABLE report_delivery DROP CONSTRAINT IF EXISTS ck_report_delivery_channel"))
    op.execute(
        sa.text(
            "ALTER TABLE report_delivery DROP CONSTRAINT IF EXISTS ck_report_delivery_ck_report_delivery_channel"
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE report_delivery
            ADD CONSTRAINT ck_report_delivery_ck_report_delivery_channel
            CHECK (channel IN ('inbox', 'email_stub'))
            """
        )
    )
