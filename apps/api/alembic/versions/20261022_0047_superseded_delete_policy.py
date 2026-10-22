"""Superseded figures: the import job delete may remove the records a deleted job owns.

Revision ID: 20261022_0047
Revises: 20261020_0046
Create Date: 2026-10-22

N-0112 (Warren 2026-10-22): deleting an import job removes the data it loaded and restores the
figures it superseded. The records in ``fact_customer_sellthrough_superseded`` and
``fact_distributor_line_superseded`` that the deleted job made, or that hold the deleted job's own
figures, go with it. Both tables were append-only (SELECT and INSERT policies under FORCE ROW LEVEL
SECURITY), so a DELETE matched no rows even for the app role.

Adds a DELETE policy in the same inline product-line form as the other policies on these tables
(20261015_0040 / 20261016_0042), and grants DELETE on the distributor table to ``cip`` (the
sell-through table already had it). Still no UPDATE policy: a record is never rewritten. No rows
change. Idempotent (``DROP POLICY IF EXISTS`` first), so it also runs after a create_all baseline.
Needs the table owner (on cip: ``postgres``): run with DATABASE_URL_SYNC_MIGRATE set to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261022_0047"
down_revision: Union[str, Sequence[str], None] = "20261020_0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("fact_customer_sellthrough_superseded", "fact_distributor_line_superseded")
EDIT_SETTING = "cip.editable_product_lines"
COLUMN = '"product_id"'


def _inline(setting: str, line_function: str) -> str:
    return (
        f"(({COLUMN}) IS NULL"
        f" OR coalesce(current_setting('{setting}', true), '') IN ('', '*')"
        f" OR ({COLUMN})::bigint IN ("
        f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)))"
    )


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS cip_pl_delete ON {table}")
        op.execute(
            f"CREATE POLICY cip_pl_delete ON {table} FOR DELETE "
            f"USING ({_inline(EDIT_SETTING, 'cip_product_line_editable')})"
        )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            GRANT DELETE ON fact_distributor_line_superseded TO cip;
            GRANT DELETE ON fact_customer_sellthrough_superseded TO cip;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP POLICY IF EXISTS cip_pl_delete ON {table}")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
            REVOKE DELETE ON fact_distributor_line_superseded FROM cip;
          END IF;
        END $$;
        """
    )
