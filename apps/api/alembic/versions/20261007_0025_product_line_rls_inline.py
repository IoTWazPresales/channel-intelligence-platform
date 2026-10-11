"""Product-line row security: inline predicates, 'no lines' sentinel, invoker view.

Revision ID: 20261007_0025
Revises: 20261006_0024
Create Date: 2026-10-07

N-0065 round 3 (N0065_PERF.md fixes 1-3, approved by Warren 2026-10-07).

1. The product-keyed policies no longer call the SECURITY DEFINER function
   ``cip_product_id_visible`` / ``cip_product_id_editable`` once per row. The
   predicate is written into the policy, so the planner inlines it: the open
   scopes (unset, '' and '*') short-circuit, and otherwise the allowed product
   ids are one hashed subplan per statement over ``dim_product``. That inner
   ``dim_product`` read runs as the caller, under ``dim_product``'s own policy,
   which is the same line rule.
2. The setting values mean:
       NULL or ''   open (workers, scripts; '' is what a pooled backend keeps
                    after a scoped transaction ended)
       '*'          every line (admin)
       '!'          no lines (a non-admin with no assignment); the app writes it
       'A,B'        only those lines
   A NULL product id stays visible. Before this revision '' meant "no lines",
   so a pooled backend that had served a request read as deny-all for the next
   unscoped user. Under 0024 the sentinel '!' is a line nobody has, so it also
   reads as "no lines": app code that writes it is correct before and after.
3. ``shipment_evidence_current`` (owned by ``postgres`` on cip, which bypasses
   row security) becomes ``security_invoker``, so the caller's policies apply
   through it. It is the only view in ``public`` over a protected table.

Needs the owner of the tables, functions and view (on cip: ``postgres``), so
run it with DATABASE_URL_SYNC_MIGRATE set to the owner connection.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261007_0025"
down_revision: Union[str, Sequence[str], None] = "20261006_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READ_SETTING = "cip.product_lines"
EDIT_SETTING = "cip.editable_product_lines"
NO_LINES = "!"

# Views in public that read a protected table (checked on cip and cip_test 2026-10-07).
INVOKER_VIEWS = ("shipment_evidence_current",)


def line_function_sql(name: str, setting: str) -> str:
    """Line test used by dim_product's policies and by the inner allowed-id read.

    Plain SQL, STABLE, no SECURITY DEFINER and no SET clause, so it inlines.
    """
    return f"""
        CREATE OR REPLACE FUNCTION {name}(line text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
          SELECT CASE
            WHEN coalesce(current_setting('{setting}', true), '') IN ('', '*') THEN true
            WHEN current_setting('{setting}', true) = '{NO_LINES}' THEN false
            ELSE line IS NOT NULL
                 AND line = ANY (string_to_array(current_setting('{setting}', true), ','))
          END
        $$
    """


def product_predicate(column: str, setting: str, line_function: str) -> str:
    """Policy expression for a product-keyed table (column is a quoted identifier)."""
    return (
        f"(({column}) IS NULL"
        f" OR coalesce(current_setting('{setting}', true), '') IN ('', '*')"
        f" OR ({column})::bigint IN ("
        f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)))"
    )


# Tables that carry the 0024 policies, with the product column 0024 chose
# (product_id before canonical_product_id).
_PROTECTED_TABLES_SQL = """
    SELECT c.table_name::text AS table_name,
           COALESCE(
             MAX(c.column_name::text) FILTER (WHERE c.column_name = 'product_id'),
             MAX(c.column_name::text) FILTER (WHERE c.column_name = 'canonical_product_id')
           ) AS column_name
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.table_schema = 'public'
      AND t.table_type = 'BASE TABLE'
      AND c.column_name IN ('product_id', 'canonical_product_id')
      AND c.data_type IN ('integer', 'bigint', 'smallint')
      AND c.table_name <> 'dim_product'
      AND EXISTS (
        SELECT 1 FROM pg_policies pp
        WHERE pp.schemaname = 'public' AND pp.tablename = c.table_name
          AND pp.policyname = 'cip_pl_select'
      )
    GROUP BY c.table_name
    ORDER BY c.table_name
"""


def protected_tables(bind) -> list[tuple[str, str]]:
    from sqlalchemy import text

    return [(r[0], r[1]) for r in bind.execute(text(_PROTECTED_TABLES_SQL)).all()]


def _quote(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _replace_policies(table: str, read_expr: str, edit_expr: str) -> None:
    t = _quote(table)
    for name in ("cip_pl_select", "cip_pl_insert", "cip_pl_update", "cip_pl_delete"):
        op.execute(f"DROP POLICY IF EXISTS {name} ON {t}")
    op.execute(f"CREATE POLICY cip_pl_select ON {t} FOR SELECT USING ({read_expr})")
    op.execute(f"CREATE POLICY cip_pl_insert ON {t} FOR INSERT WITH CHECK ({edit_expr})")
    op.execute(
        f"CREATE POLICY cip_pl_update ON {t} FOR UPDATE USING ({edit_expr}) WITH CHECK ({edit_expr})"
    )
    op.execute(f"CREATE POLICY cip_pl_delete ON {t} FOR DELETE USING ({edit_expr})")


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(line_function_sql("cip_product_line_visible", READ_SETTING))
    op.execute(line_function_sql("cip_product_line_editable", EDIT_SETTING))
    for table, column in protected_tables(bind):
        col = _quote(column)
        _replace_policies(
            table,
            product_predicate(col, READ_SETTING, "cip_product_line_visible"),
            product_predicate(col, EDIT_SETTING, "cip_product_line_editable"),
        )
    for view in INVOKER_VIEWS:
        op.execute(f"ALTER VIEW IF EXISTS public.{_quote(view)} SET (security_invoker = true)")


# --- downgrade: the 0024 definitions, verbatim in meaning ---

_LINE_FUNCTION_0024 = """
    CREATE OR REPLACE FUNCTION {name}(line text)
    RETURNS boolean
    LANGUAGE sql
    STABLE
    AS $$
      SELECT current_setting('{setting}', true) IS NULL
          OR current_setting('{setting}', true) = '*'
          OR (
            line IS NOT NULL
            AND line = ANY (string_to_array(current_setting('{setting}', true), ','))
          );
    $$
"""


def downgrade() -> None:
    bind = op.get_bind()
    for view in INVOKER_VIEWS:
        op.execute(f"ALTER VIEW IF EXISTS public.{_quote(view)} RESET (security_invoker)")
    op.execute(_LINE_FUNCTION_0024.format(name="cip_product_line_visible", setting=READ_SETTING))
    op.execute(_LINE_FUNCTION_0024.format(name="cip_product_line_editable", setting=EDIT_SETTING))
    for table, column in protected_tables(bind):
        col = _quote(column)
        _replace_policies(
            table,
            f"cip_product_id_visible(({col})::bigint)",
            f"cip_product_id_editable(({col})::bigint)",
        )
