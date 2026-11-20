"""Tenant settings: one row per tenant and key (discovery schedule switch, tenant country, ...).

Revision ID: 20261120_0064
Revises: 20261118_0063
Create Date: 2026-11-20

``tenant_setting`` holds user-set tenant configuration as jsonb. No rows are inserted here and
there are no seeded defaults: a missing row means "not set" (for ``discovery.schedule_enabled``,
off). Idempotent (created only when missing). Downgrade drops the table. Needs the table owner;
on ``cip`` run with DATABASE_URL_SYNC_MIGRATE set to the owner connection, only with Warren's
approval and after a backup. The app role ``cip`` is granted the table commands only when that
role exists.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261120_0064"
down_revision: str | Sequence[str] | None = "20261118_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_setting (
            tenant_id text NOT NULL,
            key text NOT NULL,
            value jsonb NOT NULL,
            updated_by varchar(256),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_tenant_setting PRIMARY KEY (tenant_id, key)
        )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON tenant_setting TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_setting")
