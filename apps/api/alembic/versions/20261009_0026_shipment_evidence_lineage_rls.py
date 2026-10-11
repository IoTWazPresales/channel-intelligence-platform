"""Product-line row security for shipment evidence with no product (lineage), scope-independent current row.

Revision ID: 20261009_0026
Revises: 20261007_0025
Create Date: 2026-10-09

N-0065 round 4: GOV-008 VER2 finding S3/F1 and Warren's decision of 2026-10-08.

1. ``shipment_evidence_current`` picks each identity's current observation BEFORE row
   security applies. Under 0025 the invoker view ran DISTINCT ON over the rows the caller
   could see, so when row security hid an identity's newest observation (another line), an
   older observation of the same identity with no product surfaced as "current". Now a
   scoped caller's rows are filtered by ``cip_sev_current_observation_ids()``, which picks
   the current id per identity over ALL rows. An open scope (unset, '' or '*') sees every
   row, so it keeps the 0025 plan and never calls the helper.
2. A row with no product in ``shipment_evidence_observation``, ``shipment_evidence_line``
   and ``fact_inbound_shipment`` is no longer visible to everyone. It inherits the product
   (so the product line) of its identity's latest resolved observation, and is visible when
   that product is visible. When the identity has no resolved observation it is visible only
   under an open scope (admin '*', workers) or when ``cip.request_role`` = 'steward' (bound
   by the app for signed-in requests from the server-side role). The same rule, with the
   edit setting, guards UPDATE and DELETE. INSERT and UPDATE WITH CHECK keep the 0025 rule
   (a row with no product may be written), so imports are unchanged.
   Identity of a line: the ``line_identity_key`` of the observations that point at it. Of an
   inbound row: its evidence line (the line's own product first, then the line's identity).
   The other product-keyed tables keep "no product = visible": their rows have no identity
   that resolves elsewhere.
3. The helpers are PL/pgSQL, STABLE, SECURITY INVOKER (no privilege change), with a pinned
   search_path. Each sets ``cip.product_lines`` to '*' (transaction-local) around its one
   query and restores the caller's value before returning, so it reads every row under the
   caller's own grants whoever owns the tables (cip: owner postgres; cip_test: owner cip
   with FORCE). A function-level ``SET cip.product_lines`` clause is not used: PostgreSQL
   refuses it for a placeholder setting unless the owner is a superuser (cip_test). Any SQL
   running as the app role can already set that value, so the helpers grant nothing new.
   EXECUTE is revoked from PUBLIC and granted to the roles that can read the tables.
   The policies call each helper at most once per statement (an uncorrelated hashed
   subplan), and only when a row with no product is met under a non-open scope.
4. Index ``ix_shipment_ev_obs_identity_latest`` (line_identity_key, valid_from DESC NULLS
   LAST, id DESC) INCLUDE (product_id, superseded_by_id) serves the current pick and the
   latest-resolved lookup without a sort.

Downgrade restores the 0025 policies on the three tables and the 0025 view, then drops the
helpers and the index. Run with DATABASE_URL_SYNC_MIGRATE set to the owner connection (cip).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261009_0026"
down_revision: Union[str, Sequence[str], None] = "20261007_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

READ_SETTING = "cip.product_lines"
EDIT_SETTING = "cip.editable_product_lines"
ROLE_SETTING = "cip.request_role"
STEWARD = "steward"

INDEX_NAME = "ix_shipment_ev_obs_identity_latest"

# table -> its lineage helper (all three have an integer primary key "id" and "product_id").
LINEAGE_TABLES = {
    "shipment_evidence_observation": "cip_sev_observation_lineage",
    "shipment_evidence_line": "cip_sev_line_lineage",
    "fact_inbound_shipment": "cip_inbound_shipment_lineage",
}
CURRENT_IDS_FN = "cip_sev_current_observation_ids"
HELPERS = (CURRENT_IDS_FN, *LINEAGE_TABLES.values())

_HELPER_HEAD = """
    CREATE OR REPLACE FUNCTION public.{name}()
    RETURNS TABLE (row_id bigint, inherited_product_id bigint)
    LANGUAGE plpgsql
    STABLE
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      saved_lines text := current_setting('cip.product_lines', true);
    BEGIN
      -- Read every row: this helper decides lineage independently of the caller's scope.
      -- The caller's value is restored before returning; an error aborts the
      -- (sub)transaction, which reverts the setting as well.
      PERFORM set_config('cip.product_lines', '*', true);
      RETURN QUERY
"""
_HELPER_TAIL = """;
      PERFORM set_config('cip.product_lines', coalesce(saved_lines, ''), true);
    END
    $fn$"""

# Latest resolved product of the identity whose key is in scope as {key}.
_LATEST_RESOLVED = """(
          SELECT r.product_id::bigint
          FROM public.shipment_evidence_observation r
          WHERE r.line_identity_key = {key} AND r.product_id IS NOT NULL
          ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC
          LIMIT 1)"""

HELPER_SQL = {
    CURRENT_IDS_FN: _HELPER_HEAD.format(name=CURRENT_IDS_FN) + """
      SELECT c.id::bigint, NULL::bigint
      FROM (
        SELECT DISTINCT ON (o.line_identity_key) o.id
        FROM public.shipment_evidence_observation o
        WHERE o.superseded_by_id IS NULL
        ORDER BY o.line_identity_key, o.valid_from DESC NULLS LAST, o.id DESC
      ) c""" + _HELPER_TAIL,
    "cip_sev_observation_lineage": _HELPER_HEAD.format(name="cip_sev_observation_lineage") + """
      SELECT o.id::bigint, """ + _LATEST_RESOLVED.format(key="o.line_identity_key") + """
      FROM public.shipment_evidence_observation o
      WHERE o.product_id IS NULL""" + _HELPER_TAIL,
    # Lines: identities of the observations that point at the line (joined, not correlated:
    # evidence_line_id has no index on the observation table).
    "cip_sev_line_lineage": _HELPER_HEAD.format(name="cip_sev_line_lineage") + """
      WITH nl AS (
        SELECT s.id FROM public.shipment_evidence_line s WHERE s.product_id IS NULL
      ), k AS (
        SELECT DISTINCT o.evidence_line_id, o.line_identity_key
        FROM public.shipment_evidence_observation o JOIN nl ON nl.id = o.evidence_line_id
      ), kl AS (
        SELECT k.evidence_line_id, """ + _LATEST_RESOLVED.format(key="k.line_identity_key") + """ AS pid
        FROM k
      )
      SELECT nl.id::bigint, max(kl.pid)
      FROM nl LEFT JOIN kl ON kl.evidence_line_id = nl.id
      GROUP BY nl.id""" + _HELPER_TAIL,
    # Inbound rows: the evidence line's own product first, then the line's identity.
    "cip_inbound_shipment_lineage": _HELPER_HEAD.format(name="cip_inbound_shipment_lineage") + """
      WITH ni AS (
        SELECT f.id, f.shipment_evidence_line_id AS line_id
        FROM public.fact_inbound_shipment f WHERE f.product_id IS NULL
      ), k AS (
        SELECT DISTINCT o.evidence_line_id, o.line_identity_key
        FROM public.shipment_evidence_observation o JOIN ni ON ni.line_id = o.evidence_line_id
      ), kl AS (
        SELECT k.evidence_line_id, """ + _LATEST_RESOLVED.format(key="k.line_identity_key") + """ AS pid
        FROM k
      )
      SELECT ni.id::bigint, COALESCE(max(s.product_id)::bigint, max(kl.pid))
      FROM ni
      LEFT JOIN public.shipment_evidence_line s ON s.id = ni.line_id
      LEFT JOIN kl ON kl.evidence_line_id = ni.line_id
      GROUP BY ni.id""" + _HELPER_TAIL,
}


def _allowed(setting_fn: str) -> str:
    return f"SELECT p.id FROM public.dim_product p WHERE public.{setting_fn}(p.product_line)"


def _open(setting: str) -> str:
    return f"coalesce(current_setting('{setting}', true), '') IN ('', '*')"


def lineage_predicate(setting: str, line_function: str, helper: str) -> str:
    """USING expression for a lineage table (columns product_id, id).

    Open scope; or the row's product is allowed; or the row has no product and its lineage
    product is allowed, or it has no lineage and the request is a steward.
    """
    allowed = _allowed(line_function)
    return (
        f"({_open(setting)}"
        f" OR (product_id)::bigint IN ({allowed})"
        f" OR (product_id IS NULL AND (id)::bigint IN ("
        f"SELECT m.row_id FROM public.{helper}() m"
        f" WHERE m.inherited_product_id IN ({allowed})"
        f" OR (m.inherited_product_id IS NULL"
        f" AND coalesce(current_setting('{ROLE_SETTING}', true), '') = '{STEWARD}'))))"
    )


def predicate_0025(setting: str, line_function: str) -> str:
    """The 0025 product predicate (no product = allowed), verbatim in meaning."""
    return (
        f"((product_id) IS NULL OR {_open(setting)}"
        f" OR (product_id)::bigint IN ({_allowed(line_function)}))"
    )


def _set_policies(table: str, read_using: str, edit_using: str, edit_check: str) -> None:
    for name in ("cip_pl_select", "cip_pl_insert", "cip_pl_update", "cip_pl_delete"):
        op.execute(f'DROP POLICY IF EXISTS {name} ON public."{table}"')
    op.execute(f'CREATE POLICY cip_pl_select ON public."{table}" FOR SELECT USING ({read_using})')
    op.execute(f'CREATE POLICY cip_pl_insert ON public."{table}" FOR INSERT WITH CHECK ({edit_check})')
    op.execute(
        f'CREATE POLICY cip_pl_update ON public."{table}" FOR UPDATE USING ({edit_using}) WITH CHECK ({edit_check})'
    )
    op.execute(f'CREATE POLICY cip_pl_delete ON public."{table}" FOR DELETE USING ({edit_using})')


# The view as 0009 created it (sticky POD), with {current_filter} after the supersession test.
VIEW_SQL = """
CREATE OR REPLACE VIEW public.shipment_evidence_current WITH (security_invoker = true) AS
SELECT DISTINCT ON (o.line_identity_key)
    o.id,
    o.line_identity_key,
    o.import_job_id,
    o.source_key,
    o.source_row_hash,
    o.evidence_line_id,
    o.valid_from,
    o.observed_at,
    o.superseded_by_id,
    o.source_sheet,
    o.source_row_number,
    o.report_type,
    o.line_state,
    o.raw_source_row,
    o.operating_unit,
    o.bill_to_raw,
    o.ship_to_raw,
    o.order_no,
    o.customer_po,
    COALESCE(sel.purchase_order_id, o.purchase_order_id) AS purchase_order_id,
    o.order_line,
    o.delivery_no,
    o.invoice_line,
    o.item_code,
    o.sales_model_name,
    o.customer_item,
    o.ean_code,
    o.upc_code,
    o.mpor_item_no,
    o.quantity,
    o.unit_price,
    o.amount,
    o.currency_code,
    o.ship_confirm_date,
    o.schedule_ship_date,
    o.promise_date,
    o.exwork_date,
    o.erd_date,
    o.est_pod_date,
    COALESCE(
        o.pod_date,
        sel.pod_date,
        (
            SELECT p.pod_date
            FROM shipment_evidence_observation p
            WHERE p.line_identity_key = o.line_identity_key
              AND p.pod_date IS NOT NULL
            ORDER BY p.valid_from DESC NULLS LAST, p.id DESC
            LIMIT 1
        )
    ) AS pod_date,
    COALESCE(sel.product_id, o.product_id) AS product_id,
    COALESCE(sel.product_resolution_status, o.product_resolution_status) AS product_resolution_status,
    COALESCE(sel.product_resolution_token, o.product_resolution_token) AS product_resolution_token,
    COALESCE(sel.product_resolution_detail, o.product_resolution_detail) AS product_resolution_detail,
    COALESCE(sel.distributor_id, o.distributor_id) AS distributor_id,
    COALESCE(sel.distributor_resolution_status, o.distributor_resolution_status) AS distributor_resolution_status,
    COALESCE(sel.distributor_resolution_token, o.distributor_resolution_token) AS distributor_resolution_token,
    o.customer_dealer_token,
    COALESCE(sel.resolved_customer_id, sel.customer_id, o.customer_id) AS customer_id,
    COALESCE(sel.customer_resolution_status, o.customer_resolution_status) AS customer_resolution_status,
    sel.resolved_customer_id,
    sel.resolved_distributor_id,
    sel.crad_date,
    o.created_at,
    o.updated_at
FROM shipment_evidence_observation o
LEFT JOIN shipment_evidence_line sel ON sel.id = o.evidence_line_id
WHERE o.superseded_by_id IS NULL{current_filter}
ORDER BY o.line_identity_key, o.valid_from DESC NULLS LAST, o.id DESC
"""

# Scoped callers: only each identity's current observation (picked over all rows).
CURRENT_FILTER = (
    f"\n  AND ({_open(READ_SETTING)}"
    f"\n       OR o.id IN (SELECT c.row_id FROM public.{CURRENT_IDS_FN}() c))"
)


def _grant_helpers(bind) -> None:
    from sqlalchemy import text

    grantees = [
        r[0]
        for r in bind.execute(
            text(
                """
                SELECT DISTINCT grantee FROM information_schema.role_table_grants
                WHERE table_schema = 'public' AND privilege_type = 'SELECT'
                  AND table_name IN ('shipment_evidence_observation', 'shipment_evidence_line',
                                     'fact_inbound_shipment', 'shipment_evidence_current')
                """
            )
        ).all()
    ]
    for fn in HELPERS:
        op.execute(f"REVOKE ALL ON FUNCTION public.{fn}() FROM PUBLIC")
        for g in grantees:
            who = "PUBLIC" if g == "PUBLIC" else '"' + g.replace('"', '""') + '"'
            op.execute(f"GRANT EXECUTE ON FUNCTION public.{fn}() TO {who}")


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON public.shipment_evidence_observation "
        "(line_identity_key, valid_from DESC NULLS LAST, id DESC) INCLUDE (product_id, superseded_by_id)"
    )
    for fn in HELPERS:
        op.execute(HELPER_SQL[fn])
    _grant_helpers(bind)
    for table, helper in LINEAGE_TABLES.items():
        _set_policies(
            table,
            lineage_predicate(READ_SETTING, "cip_product_line_visible", helper),
            lineage_predicate(EDIT_SETTING, "cip_product_line_editable", helper),
            predicate_0025(EDIT_SETTING, "cip_product_line_editable"),
        )
    op.execute(VIEW_SQL.format(current_filter=CURRENT_FILTER))


def downgrade() -> None:
    # 0025 view first (it stops referencing the helper), then the 0025 policies, then drop.
    op.execute(VIEW_SQL.format(current_filter=""))
    for table in LINEAGE_TABLES:
        _set_policies(
            table,
            predicate_0025(READ_SETTING, "cip_product_line_visible"),
            predicate_0025(EDIT_SETTING, "cip_product_line_editable"),
            predicate_0025(EDIT_SETTING, "cip_product_line_editable"),
        )
    for fn in HELPERS:
        op.execute(f"DROP FUNCTION IF EXISTS public.{fn}()")
    op.execute(f"DROP INDEX IF EXISTS public.{INDEX_NAME}")
