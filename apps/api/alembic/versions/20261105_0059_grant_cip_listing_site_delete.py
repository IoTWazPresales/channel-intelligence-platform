"""Grant the app role cip DELETE on listing_site.

Revision ID: 20261105_0059
Revises: 20261105_0058
Create Date: 2026-11-05

``20261103_0053`` grants ``listing_site`` SELECT, INSERT, and UPDATE only
(sites are deactivated in product code; the table still has no DELETE grant).
``cip`` on cip_test can read and write rows but cannot delete them, so
``test_listing_sites_api`` teardown and its viewer-403 test fail.

Idempotent. No-op when role ``cip`` is absent, and when ``listing_site`` is
absent. The serial sequence is granted the same way. No schema, row-security,
or policy change. Downgrade revokes exactly these privileges, with the same
guards.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261105_0059"
down_revision: Union[str, Sequence[str], None] = "20261105_0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("listing_site",)


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
