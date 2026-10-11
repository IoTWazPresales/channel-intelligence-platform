"""Current-row pick in index order; rows with no product in four tables for admins and stewards only.

Revision ID: 20261009_0027
Revises: 20261009_0026
Create Date: 2026-10-09

N-0065 round 5, Warren's decision of 2026-10-09.

(a) ``cip_sev_current_observation_ids()`` (the scope-independent current pick that
    ``shipment_evidence_current`` uses for scoped callers) gets a function-level
    ``SET enable_sort = off``. Its one query (DISTINCT ON line_identity_key ORDER BY
    line_identity_key, valid_from DESC NULLS LAST, id DESC) then walks
    ``ix_shipment_ev_obs_identity_latest`` in order with an ordered index-only scan instead
    of a seq scan plus an external sort (cip, READ ONLY: 566 ms -> 64 ms).
    Why this option rather than a rewrite that forces index order: it changes only the plan,
    never the result (the query text and its semantics are untouched), it is scoped to the
    function call and restored by PostgreSQL on exit, including on error, ``enable_sort`` is
    a USERSET parameter (allowed for a non-superuser owner, unlike the placeholder setting
    0026 had to manage by hand), and if the index were ever missing the planner still sorts
    (correct, only slower). The downgrade is a RESET of each setting.
    ``enable_incremental_sort = off`` is set too: on PostgreSQL 18 ``enable_sort`` does not
    govern Incremental Sort, and with a stale visibility map (rows written since the last
    vacuum) the planner was seen on cip_test choosing an Incremental Sort over
    ``ix_shipment_ev_obs_line_identity`` instead. With both off, the ordered walk of
    ``ix_shipment_ev_obs_identity_latest`` (index-only when the visibility map allows, else
    an index scan) is the only plan with no disabled node.
    The three lineage helpers were checked for the same change and are NOT changed: they
    already use the index for the per-identity lookup, and ``enable_sort = off`` made them
    no faster (observation lineage 129 -> 134 ms, line lineage 173 -> 185 ms; with hash
    aggregation also off the line lineage exceeded 60 s).
(b) ``commercial_lineup_line``, ``cst_listing_seed``, ``customer_listing`` and
    ``historical_lineup_import_line``: a row with no product is no longer visible to every
    scope. It is visible (and, with the edit setting, updatable/deletable) only under an open
    scope (unset: workers; '' : pooled leftover; '*': admins) or when ``cip.request_role`` is
    'steward' -- the same rule as truly unresolved shipment evidence rows in 0026. Rows with
    a product keep the 0025 rule. INSERT and UPDATE WITH CHECK keep the 0025 rule (a row
    with no product may be written), so imports in workers are unchanged. These tables have
    no identity that resolves elsewhere (0026 discovery), so there is no inheritance.
``fact_inbound_shipment`` stays as in 0026.

Downgrade: RESET enable_sort and enable_incremental_sort on the pick, and the 0025 policies on the four tables.
Run with DATABASE_URL_SYNC_MIGRATE set to the owner connection (cip).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261009_0027"
down_revision: Union[str, Sequence[str], None] = "20261009_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READ_SETTING = "cip.product_lines"
EDIT_SETTING = "cip.editable_product_lines"
ROLE_SETTING = "cip.request_role"
STEWARD = "steward"

PICK_FN = "cip_sev_current_observation_ids"
PICK_SETTINGS = ("enable_sort", "enable_incremental_sort")  # each set to off on the pick

# Tables whose rows with no product become admin/steward only (product column: product_id).
NO_PRODUCT_STEWARD_TABLES = (
    "commercial_lineup_line",
    "cst_listing_seed",
    "customer_listing",
    "historical_lineup_import_line",
)
PRODUCT_COLUMN = '"product_id"'


def _open(setting: str) -> str:
    return f"coalesce(current_setting('{setting}', true), '') IN ('', '*')"


def _allowed(line_function: str) -> str:
    return f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)"


def steward_predicate(setting: str, line_function: str) -> str:
    """USING for the four tables: open scope; or the product is allowed; or no product and steward."""
    col = PRODUCT_COLUMN
    return (
        f"({_open(setting)}"
        f" OR ({col})::bigint IN ({_allowed(line_function)})"
        f" OR (({col}) IS NULL AND coalesce(current_setting('{ROLE_SETTING}', true), '') = '{STEWARD}'))"
    )


def predicate_0025(setting: str, line_function: str) -> str:
    """0025's product_predicate for column "product_id", verbatim."""
    col = PRODUCT_COLUMN
    return (
        f"(({col}) IS NULL"
        f" OR coalesce(current_setting('{setting}', true), '') IN ('', '*')"
        f" OR ({col})::bigint IN ("
        f"SELECT p.id FROM public.dim_product p WHERE public.{line_function}(p.product_line)))"
    )


def _set_policies(table: str, read_using: str, edit_using: str, edit_check: str) -> None:
    t = f'public."{table}"'
    for name in ("cip_pl_select", "cip_pl_insert", "cip_pl_update", "cip_pl_delete"):
        op.execute(f"DROP POLICY IF EXISTS {name} ON {t}")
    op.execute(f"CREATE POLICY cip_pl_select ON {t} FOR SELECT USING ({read_using})")
    op.execute(f"CREATE POLICY cip_pl_insert ON {t} FOR INSERT WITH CHECK ({edit_check})")
    op.execute(f"CREATE POLICY cip_pl_update ON {t} FOR UPDATE USING ({edit_using}) WITH CHECK ({edit_check})")
    op.execute(f"CREATE POLICY cip_pl_delete ON {t} FOR DELETE USING ({edit_using})")


def _check_tables(bind) -> None:
    from sqlalchemy import text

    for table in NO_PRODUCT_STEWARD_TABLES:
        ok = bind.execute(
            text(
                """select exists (select 1 from information_schema.columns
                   where table_schema = 'public' and table_name = :t and column_name = 'product_id')
                   and exists (select 1 from pg_policies where schemaname = 'public' and tablename = :t
                               and policyname = 'cip_pl_select')"""
            ),
            {"t": table},
        ).scalar_one()
        if not ok:
            raise RuntimeError(f"{table}: expected column product_id and the cip_pl_* policies (0025)")


def upgrade() -> None:
    bind = op.get_bind()
    for setting in PICK_SETTINGS:
        op.execute(f"ALTER FUNCTION public.{PICK_FN}() SET {setting} = off")
    _check_tables(bind)
    for table in NO_PRODUCT_STEWARD_TABLES:
        _set_policies(
            table,
            steward_predicate(READ_SETTING, "cip_product_line_visible"),
            steward_predicate(EDIT_SETTING, "cip_product_line_editable"),
            predicate_0025(EDIT_SETTING, "cip_product_line_editable"),
        )


def downgrade() -> None:
    for table in NO_PRODUCT_STEWARD_TABLES:
        _set_policies(
            table,
            predicate_0025(READ_SETTING, "cip_product_line_visible"),
            predicate_0025(EDIT_SETTING, "cip_product_line_editable"),
            predicate_0025(EDIT_SETTING, "cip_product_line_editable"),
        )
    for setting in PICK_SETTINGS:
        op.execute(f"ALTER FUNCTION public.{PICK_FN}() RESET {setting}")
