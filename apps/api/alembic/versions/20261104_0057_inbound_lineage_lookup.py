"""Inbound lineage helper looks up each line instead of scanning evidence.

Revision ID: 20261104_0057
Revises: 20261103_0056
Create Date: 2026-11-04

``cip_inbound_shipment_lineage()`` is the row-security helper for inbound rows
with no product (20261009_0026). Its body joined every evidence line and every
observation, then hashed. On cip that was 0.741s for 765 rows, and a line-scoped
brief or cover statement pays it once per scan of ``fact_inbound_shipment``.

The same rows come back from the line's own product, then the latest resolved
product of each of that line's identity keys. ``ix_shipment_ev_obs_evidence_line``
and ``ix_shipment_ev_obs_identity_latest`` already exist, so this is not a new
index. Read-only on cip: 765 rows, identical to the old function, 0.092s.

Not applied to cip. Prove on cip_test, then Warren applies it to cip.
Downgrade restores the 0026 body. Grants stay (CREATE OR REPLACE keeps them).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261104_0057"
down_revision: Union[str, Sequence[str], None] = "20261103_0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HEAD = """
    CREATE OR REPLACE FUNCTION public.cip_inbound_shipment_lineage()
    RETURNS TABLE (row_id bigint, inherited_product_id bigint)
    LANGUAGE plpgsql
    STABLE
    SET search_path = pg_catalog, public
    AS $fn$
    DECLARE
      saved_lines text := current_setting('cip.product_lines', true);
    BEGIN
      PERFORM set_config('cip.product_lines', '*', true);
      RETURN QUERY
"""

_TAIL = """;
      PERFORM set_config('cip.product_lines', coalesce(saved_lines, ''), true);
    END
    $fn$"""

_NEW_BODY = """
      WITH ni AS MATERIALIZED (
        SELECT f.id, f.shipment_evidence_line_id AS line_id
        FROM public.fact_inbound_shipment f
        WHERE f.product_id IS NULL
      )
      SELECT ni.id::bigint,
             COALESCE(
               (SELECT s.product_id::bigint
                FROM public.shipment_evidence_line s
                WHERE s.id = ni.line_id),
               (
                 SELECT max(one.pid)
                 FROM (
                   SELECT DISTINCT ON (o.line_identity_key) (
                     SELECT r.product_id::bigint
                     FROM public.shipment_evidence_observation r
                     WHERE r.line_identity_key = o.line_identity_key
                       AND r.product_id IS NOT NULL
                     ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC
                     LIMIT 1
                   ) AS pid
                   FROM public.shipment_evidence_observation o
                   WHERE o.evidence_line_id = ni.line_id
                   ORDER BY o.line_identity_key
                 ) one
               )
             )
      FROM ni"""

_OLD_BODY = """
      WITH ni AS (
        SELECT f.id, f.shipment_evidence_line_id AS line_id
        FROM public.fact_inbound_shipment f WHERE f.product_id IS NULL
      ), k AS (
        SELECT DISTINCT o.evidence_line_id, o.line_identity_key
        FROM public.shipment_evidence_observation o JOIN ni ON ni.line_id = o.evidence_line_id
      ), kl AS (
        SELECT k.evidence_line_id, (
          SELECT r.product_id::bigint
          FROM public.shipment_evidence_observation r
          WHERE r.line_identity_key = k.line_identity_key AND r.product_id IS NOT NULL
          ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC
          LIMIT 1) AS pid
        FROM k
      )
      SELECT ni.id::bigint, COALESCE(max(s.product_id)::bigint, max(kl.pid))
      FROM ni
      LEFT JOIN public.shipment_evidence_line s ON s.id = ni.line_id
      LEFT JOIN kl ON kl.evidence_line_id = ni.line_id
      GROUP BY ni.id"""


def upgrade() -> None:
    op.execute(_HEAD + _NEW_BODY + _TAIL)


def downgrade() -> None:
    op.execute(_HEAD + _OLD_BODY + _TAIL)
