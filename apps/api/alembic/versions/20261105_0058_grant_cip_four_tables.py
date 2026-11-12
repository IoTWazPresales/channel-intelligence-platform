"""Grant the app role cip DML on four tables created without a grant.

Revision ID: 20261105_0058
Revises: 20261104_0057
Create Date: 2026-11-05

``20261103_0052`` creates ``user_customer_account`` and ``20261103_0054`` creates
``site_candidate``, ``dc_served_account``, and ``store_dc_tenant_config`` with no
GRANT. ``20261103_0053`` grants only the tables it passes to its policies helper.
Earlier revisions grant every new table to ``cip``.

Idempotent. No-op when role ``cip`` is absent, and per table when that table is
absent. Serial/identity sequences owned by those tables are granted the same way
(``store_dc_tenant_config`` has none). No schema, row-security, or policy change.
Downgrade revokes exactly these privileges, with the same guards.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261105_0058"
down_revision: Union[str, Sequence[str], None] = "20261104_0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "user_customer_account",
    "site_candidate",
    "dc_served_account",
    "store_dc_tenant_config",
)


def _apply(*, grant: bool) -> None:
    table_sql = (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public."
        if grant
        else "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE public."
    )
    table_tail = " TO cip" if grant else " FROM cip"
    seq_sql = (
        "GRANT USAGE, SELECT ON SEQUENCE public."
        if grant
        else "REVOKE USAGE, SELECT ON SEQUENCE public."
    )
    seq_tail = " TO cip" if grant else " FROM cip"
    names = ",".join(_TABLES)
    op.execute(
        f"""
        DO $$
        DECLARE
          tbl text;
          seq text;
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            RETURN;
          END IF;
          FOREACH tbl IN ARRAY '{{{names}}}'::text[]
          LOOP
            IF to_regclass('public.' || tbl) IS NULL THEN
              CONTINUE;
            END IF;
            EXECUTE '{table_sql}' || quote_ident(tbl) || '{table_tail}';
            FOR seq IN
              SELECT s.relname
              FROM pg_class AS s
              JOIN pg_namespace AS ns ON ns.oid = s.relnamespace
              JOIN pg_depend AS d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
              JOIN pg_class AS t ON t.oid = d.refobjid
              JOIN pg_namespace AS nt ON nt.oid = t.relnamespace
              WHERE s.relkind = 'S'
                AND ns.nspname = 'public'
                AND nt.nspname = 'public'
                AND t.relname = tbl
            LOOP
              EXECUTE '{seq_sql}' || quote_ident(seq) || '{seq_tail}';
            END LOOP;
          END LOOP;
        END $$;
        """
    )


def upgrade() -> None:
    _apply(grant=True)


def downgrade() -> None:
    _apply(grant=False)
