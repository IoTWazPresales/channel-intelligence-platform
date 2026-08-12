"""Widen cpor payment credit_note_id for multi-CN cells.

ASUS Pending Report packs many CN ids into one cell (semicolon-separated),
up to ~480 chars — VARCHAR(128) truncates on stage.

Revision ID: 20260812_0014
Revises: 20260812_0013
Create Date: 2026-08-12
"""

from __future__ import annotations

from alembic import op

revision = "20260812_0014"
down_revision = "20260812_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE import_cpor_payment_staging_line
          ALTER COLUMN credit_note_id TYPE VARCHAR(512)
        """
    )
    op.execute(
        """
        ALTER TABLE cpor_payment_evidence
          ALTER COLUMN credit_note_id TYPE VARCHAR(512)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE cpor_payment_evidence
          ALTER COLUMN credit_note_id TYPE VARCHAR(128)
        """
    )
    op.execute(
        """
        ALTER TABLE import_cpor_payment_staging_line
          ALTER COLUMN credit_note_id TYPE VARCHAR(128)
        """
    )
