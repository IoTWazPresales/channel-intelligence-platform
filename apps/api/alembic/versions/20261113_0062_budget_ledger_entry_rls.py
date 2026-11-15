"""Product-line row security on budget_ledger_entry.

Revision ID: 20261113_0062
Revises: 20261110_0061
Create Date: 2026-11-13

Truth audit 2026-11-12 (F-RLS): ``budget_ledger_entry`` (20261012_0033) was created after
20261006_0024 turned on product-line row security for every table with a ``product_id`` column,
so it never got it: row security is off there, and every signed-in user reads every line's
ledger rows. This applies the same rule the other product tables follow (D-0056), in the inline
form of 20261007_0025 / 20261015_0040: a row is visible when its product's line is visible,
the scope is open (unset, '' or '*'), or the row has no product.

The ledger is append-only (the app role has SELECT and INSERT only, and a trigger refuses UPDATE
and DELETE), so, like ``fact_customer_sellthrough_superseded`` in 0040, it gets SELECT and INSERT
policies only.

Rows with no product (transfer, cap and paid rows) stay visible to every user, as on every other
product-keyed table. No data is touched. Idempotent: a policy that is already there is kept.
Needs the table owner (on cip: ``postgres``), so run it with DATABASE_URL_SYNC_MIGRATE set to the
owner connection.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261113_0062"
down_revision: Union[str, Sequence[str], None] = "20261110_0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "budget_ledger_entry"
READ_SETTING = "cip.product_lines"
EDIT_SETTING = "cip.editable_product_lines"
COLUMN = '"product_id"'
POLICIES = ("cip_pl_select", "cip_pl_insert")


def _inline(setting: str, line_function: str) -> str:
    """The 0025 predicate for a product-keyed table."""
    return (
        f"(({COLUMN}) IS NULL"
        f" OR coalesce(current_setting('{setting}', true), '') IN ('', '*')"
        f" OR ({COLUMN})::bigint IN ("
        f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)))"
    )


def _add_policy_if_missing(name: str, statement: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = '{TABLE}'
              AND policyname = '{name}'
          ) THEN
            EXECUTE $policy${statement}$policy$;
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    _add_policy_if_missing(
        "cip_pl_select",
        f"CREATE POLICY cip_pl_select ON {TABLE} FOR SELECT "
        f"USING ({_inline(READ_SETTING, 'cip_product_line_visible')})",
    )
    _add_policy_if_missing(
        "cip_pl_insert",
        f"CREATE POLICY cip_pl_insert ON {TABLE} FOR INSERT "
        f"WITH CHECK ({_inline(EDIT_SETTING, 'cip_product_line_editable')})",
    )


def downgrade() -> None:
    for name in POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {TABLE}")
    op.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
