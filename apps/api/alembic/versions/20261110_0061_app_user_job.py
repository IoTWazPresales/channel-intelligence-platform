"""N-0100 part B: a nullable job on app_user, separate from role.

Revision ID: 20261110_0061
Revises: 20261105_0060
Create Date: 2026-11-10

One of account_manager, product_manager, finance, country_manager, admin, or NULL. No new role
value; role and require_roles are unchanged. Existing users get NULL (no job). Idempotent.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261110_0061"
down_revision: Union[str, Sequence[str], None] = "20261105_0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE app_user ADD COLUMN IF NOT EXISTS job text")
    op.execute("ALTER TABLE app_user DROP CONSTRAINT IF EXISTS ck_app_user_job")
    op.execute(
        "ALTER TABLE app_user ADD CONSTRAINT ck_app_user_job CHECK (job IS NULL OR job IN "
        "('account_manager', 'product_manager', 'finance', 'country_manager', 'admin'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE app_user DROP CONSTRAINT IF EXISTS ck_app_user_job")
    op.execute("ALTER TABLE app_user DROP COLUMN IF EXISTS job")
