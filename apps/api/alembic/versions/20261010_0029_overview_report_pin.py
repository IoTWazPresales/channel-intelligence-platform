"""Per-user pins of saved reports onto Overview.

Revision ID: 20261010_0029
Revises: 20261010_0028
Create Date: 2026-10-10

One row per user and saved report. Deleting the user or the report removes the pin.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261010_0029"
down_revision: Union[str, Sequence[str], None] = "20261010_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS overview_report_pin (
            id bigserial PRIMARY KEY,
            user_id bigint NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            saved_report_id bigint NOT NULL REFERENCES saved_report(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_overview_report_pin_user_report UNIQUE (user_id, saved_report_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_overview_report_pin_user_id ON overview_report_pin (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_overview_report_pin_saved_report_id ON overview_report_pin (saved_report_id)"
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON overview_report_pin TO cip;
        GRANT USAGE, SELECT ON SEQUENCE overview_report_pin_id_seq TO cip;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS overview_report_pin")
