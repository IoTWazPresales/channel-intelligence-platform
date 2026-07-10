"""Plan D cutover: corpus supersede marker, shipment_evidence_current view + GRANT.

Revision ID: 20260702_0066
Revises: 20260701_0065
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260702_0066"
down_revision: Union[str, Sequence[str], None] = "20260701_0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CURRENT_VIEW_SQL = """
CREATE VIEW shipment_evidence_current AS
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
    o.pod_date,
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
ORDER BY o.line_identity_key, o.valid_from DESC NULLS LAST, o.id DESC
"""


def upgrade() -> None:
    op.add_column(
        "shipment_evidence_line",
        sa.Column("corpus_superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_shipment_evidence_line_active_corpus",
        "shipment_evidence_line",
        ["import_job_id"],
        postgresql_where=sa.text("corpus_superseded_at IS NULL"),
    )

    op.execute(sa.text("DROP VIEW IF EXISTS shipment_evidence_current"))
    op.execute(sa.text(_CURRENT_VIEW_SQL))
    op.execute(sa.text("GRANT SELECT ON shipment_evidence_current TO cip"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE ON shipment_evidence_observation TO cip"
        )
    )
    op.execute(
        sa.text(
            "GRANT USAGE, SELECT ON SEQUENCE shipment_evidence_observation_id_seq TO cip"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP VIEW IF EXISTS shipment_evidence_current"))
    op.execute(
        sa.text(
            """
            CREATE VIEW shipment_evidence_current AS
            SELECT DISTINCT ON (line_identity_key)
                o.*
            FROM shipment_evidence_observation o
            ORDER BY line_identity_key, valid_from DESC NULLS LAST, id DESC
            """
        )
    )
    op.drop_index("ix_shipment_evidence_line_active_corpus", table_name="shipment_evidence_line")
    op.drop_column("shipment_evidence_line", "corpus_superseded_at")
