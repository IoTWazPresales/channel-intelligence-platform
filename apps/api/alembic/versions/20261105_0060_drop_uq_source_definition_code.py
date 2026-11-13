"""Drop global unique uq_source_definition_code on source_definition(code).

Revision ID: 20261105_0060
Revises: 20261105_0059
Create Date: 2026-11-05

``20261103_0055`` dropped constraint ``source_definition_code_key`` and added
``uq_source_definition_tenant_code`` on ``(tenant_id, code)``. The SQLAlchemy
naming-convention unique ``uq_source_definition_code`` (``uq_%(table_name)s_%(column_0_name)s``)
on ``(code)`` alone was left in place, so two tenants cannot share a
``source_definition.code``.

Idempotent. Drops that name only when ``pg_constraint`` or ``pg_indexes``
shows it on ``source_definition``. Does not create, drop, or alter
``uq_source_definition_tenant_code``.

Downgrade recreates the unique on ``(code)`` only when that name is absent
and no duplicate ``code`` values exist. Duplicate codes: skip (see the
comment in ``downgrade``). ``uq_source_definition_tenant_code`` is not touched.

Applied to cip (truth audit 2026-11-12: cip is at 20261110_0061, which follows this revision,
and ``uq_source_definition_tenant_code`` is in place).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261105_0060"
down_revision: Union[str, Sequence[str], None] = "20261105_0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME = "uq_source_definition_code"
_TABLE = "source_definition"


def upgrade() -> None:
    # Presence checks cover both shapes of this name: a UNIQUE constraint
    # (pg_constraint, whose backing index shares the name) and a standalone
    # unique index (pg_indexes only). Drop the constraint first so PostgreSQL
    # does not reject DROP INDEX on a constraint-owned index.
    # uq_source_definition_tenant_code is a different name and is not dropped.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.{_TABLE}') IS NULL THEN
            RETURN;
          END IF;

          IF EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = '{_NAME}'
              AND conrelid = 'public.{_TABLE}'::regclass
          ) THEN
            ALTER TABLE public.{_TABLE} DROP CONSTRAINT {_NAME};
          END IF;

          IF EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = '{_TABLE}'
              AND indexname = '{_NAME}'
          ) THEN
            DROP INDEX public.{_NAME};
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Symmetrical guards: recreate only when neither the constraint nor the
    # index of this name exists. Skip when any code value is duplicated.
    # uq_source_definition_tenant_code is not created or dropped here.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.{_TABLE}') IS NULL THEN
            RETURN;
          END IF;

          IF EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = '{_NAME}'
              AND conrelid = 'public.{_TABLE}'::regclass
          ) OR EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = '{_TABLE}'
              AND indexname = '{_NAME}'
          ) THEN
            RETURN;
          END IF;

          IF EXISTS (
            SELECT 1
            FROM public.{_TABLE}
            GROUP BY code
            HAVING COUNT(*) > 1
          ) THEN
            -- Duplicate source_definition.code values exist, so a unique on
            -- (code) alone cannot be restored. Skip recreating
            -- uq_source_definition_code. uq_source_definition_tenant_code
            -- stays as the tenant-scoped unique and is not modified.
            RETURN;
          END IF;

          ALTER TABLE public.{_TABLE}
            ADD CONSTRAINT {_NAME} UNIQUE (code);
        END $$;
        """
    )
