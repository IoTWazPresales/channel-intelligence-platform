"""The installed inbound lineage helper matches the line-index lookup. cip_test only."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

_LOOKUP = """
WITH ni AS MATERIALIZED (
  SELECT f.id, f.shipment_evidence_line_id AS line_id
  FROM public.fact_inbound_shipment f
  WHERE f.product_id IS NULL
)
SELECT ni.id::bigint AS row_id,
       COALESCE(
         (SELECT s.product_id::bigint FROM public.shipment_evidence_line s WHERE s.id = ni.line_id),
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
       ) AS inherited_product_id
FROM ni
"""


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def test_inbound_lineage_matches_the_line_lookup(session: Session) -> None:
    present = session.execute(
        text("SELECT to_regprocedure('public.cip_inbound_shipment_lineage()')")
    ).scalar()
    if present is None:
        pytest.skip("cip_inbound_shipment_lineage is not installed")
    body = session.execute(
        text("SELECT pg_get_functiondef('public.cip_inbound_shipment_lineage()'::regprocedure)")
    ).scalar()
    assert "o.evidence_line_id = ni.line_id" in str(body)
    session.execute(text("SELECT set_config('cip.product_lines', '*', true)"))
    mismatch = session.execute(
            text(
                f"""
                SELECT count(*) FROM (
                  (SELECT row_id, inherited_product_id FROM public.cip_inbound_shipment_lineage()
                   EXCEPT
                   SELECT row_id, inherited_product_id FROM ({_LOOKUP}) lookup)
                  UNION ALL
                  (SELECT row_id, inherited_product_id FROM ({_LOOKUP}) lookup
                   EXCEPT
                   SELECT row_id, inherited_product_id FROM public.cip_inbound_shipment_lineage())
                ) differ
                """
            )
    ).scalar()
    assert int(mismatch or 0) == 0
