"""Private UI layouts per tenant, authenticated user and layout key.

Revision ID: 20261120_0065
Revises: 20261120_0064
Create Date: 2026-11-20

No seeded rows. Idempotent creation and conditional app-role grants follow 0064.
The API derives both owner fields from the authenticated account; neither is
accepted in the request body. No application data is changed by this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261120_0065"
down_revision: str | Sequence[str] | None = "20261120_0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.user_ui_layout (
            tenant_id text NOT NULL REFERENCES public.tenant (id) ON DELETE CASCADE,
            user_id bigint NOT NULL REFERENCES public.app_user (id) ON DELETE CASCADE,
            key text NOT NULL,
            value jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_user_ui_layout PRIMARY KEY (tenant_id, user_id, key),
            CONSTRAINT ck_user_ui_layout_key
                CHECK (key ~ '^[a-z][a-z0-9_.-]{0,79}$'),
            CONSTRAINT ck_user_ui_layout_value
                CHECK (jsonb_typeof(value) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_ui_layout_user_id
            ON public.user_ui_layout (user_id)
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT, UPDATE ON public.user_ui_layout TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.user_ui_layout")
