"""Single-use account invite links.

Revision ID: 20261010_0028
Revises: 20261009_0027
Create Date: 2026-10-10

Stores only the hash of a set-password token. The raw token is emailed once
and is not a column. Links expire after 72 hours and are single-use.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261010_0028"
down_revision: Union[str, Sequence[str], None] = "20261009_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS app_user_invite (
            id bigserial PRIMARY KEY,
            user_id bigint NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            token_hash text NOT NULL,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            used_at timestamptz NULL,
            CONSTRAINT uq_app_user_invite_token_hash UNIQUE (token_hash)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_app_user_invite_user_id ON app_user_invite (user_id)"
    )
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE ON app_user_invite TO cip;
        GRANT USAGE, SELECT ON SEQUENCE app_user_invite_id_seq TO cip;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_user_invite")
