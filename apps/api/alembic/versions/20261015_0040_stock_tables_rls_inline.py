"""Inline product-line row security on the two N-0110 tables.

Revision ID: 20261015_0040
Revises: 20261015_0039
Create Date: 2026-10-15

N-0096. ``customer_stock_position`` (20261014_0037) and ``fact_customer_sellthrough_superseded``
(20261015_0038) were created with the 0024 function-form policies
(``cip_product_id_visible`` / ``cip_product_id_editable``, a SECURITY DEFINER call per row).
20261007_0025 replaced that form on every other protected table with the inline predicate the
planner can hash (open scopes short-circuit, otherwise one subplan over ``dim_product``), and the
parity test expects every protected table to behave the same. This moves both tables to the
inline form. Warren allowed it 2026-10-15.

Row visibility is unchanged for every product id that has a ``dim_product`` row, which both
tables' foreign key guarantees. The one difference is by design: under an open scope, a product
id with no ``dim_product`` row is now visible and writable (0025: "open means open") instead of
hidden.

``fact_customer_sellthrough_superseded`` stays append-only: SELECT and INSERT policies only.
No data is touched. Needs the table owner (on cip: ``postgres``), so run it with
DATABASE_URL_SYNC_MIGRATE set to the owner connection.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261015_0040"
down_revision: Union[str, Sequence[str], None] = "20261015_0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READ_SETTING = "cip.product_lines"
EDIT_SETTING = "cip.editable_product_lines"
COLUMN = '"product_id"'

# table -> policy commands it carries
_TABLES = {
    "customer_stock_position": ("select", "insert", "update", "delete"),
    "fact_customer_sellthrough_superseded": ("select", "insert"),
}


def _inline(setting: str, line_function: str) -> str:
    """The 0025 predicate for a product-keyed table."""
    return (
        f"(({COLUMN}) IS NULL"
        f" OR coalesce(current_setting('{setting}', true), '') IN ('', '*')"
        f" OR ({COLUMN})::bigint IN ("
        f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)))"
    )


def _function_form(kind: str) -> str:
    return f"cip_product_id_{kind}(({COLUMN})::bigint)"


def _replace(table: str, read_expr: str, edit_expr: str) -> None:
    for name in ("cip_pl_select", "cip_pl_insert", "cip_pl_update", "cip_pl_delete"):
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    cmds = _TABLES[table]
    if "select" in cmds:
        op.execute(f"CREATE POLICY cip_pl_select ON {table} FOR SELECT USING ({read_expr})")
    if "insert" in cmds:
        op.execute(f"CREATE POLICY cip_pl_insert ON {table} FOR INSERT WITH CHECK ({edit_expr})")
    if "update" in cmds:
        op.execute(
            f"CREATE POLICY cip_pl_update ON {table} FOR UPDATE "
            f"USING ({edit_expr}) WITH CHECK ({edit_expr})"
        )
    if "delete" in cmds:
        op.execute(f"CREATE POLICY cip_pl_delete ON {table} FOR DELETE USING ({edit_expr})")


def upgrade() -> None:
    for table in _TABLES:
        _replace(
            table,
            _inline(READ_SETTING, "cip_product_line_visible"),
            _inline(EDIT_SETTING, "cip_product_line_editable"),
        )


def downgrade() -> None:
    for table in _TABLES:
        _replace(table, _function_form("visible"), _function_form("editable"))
