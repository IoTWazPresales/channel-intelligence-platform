"""Append-only platform audit for admin, user, settings and case-state actions.

Revision ID: 20261011_0031
Revises: 20261011_0030
Create Date: 2026-10-11

The app role may insert and read. It may not update or delete rows.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261011_0031"
down_revision: Union[str, Sequence[str], None] = "20261011_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_audit_event (
            id bigserial PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            tenant_id text NOT NULL REFERENCES tenant(id) ON DELETE RESTRICT,
            actor_user_id bigint REFERENCES app_user(id) ON DELETE SET NULL,
            actor text NOT NULL,
            area text NOT NULL,
            action text NOT NULL,
            target_type text,
            target_id text,
            detail_json jsonb,
            CONSTRAINT ck_platform_audit_event_area
                CHECK (area IN ('admin', 'user', 'settings', 'case'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_platform_audit_event_tenant_created
            ON platform_audit_event (tenant_id, created_at DESC)
        """
    )
    op.execute(
        """
        GRANT SELECT, INSERT ON platform_audit_event TO cip;
        GRANT USAGE, SELECT ON SEQUENCE platform_audit_event_id_seq TO cip;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_audit_event")
