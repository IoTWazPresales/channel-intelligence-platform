"""Bitemporal shipment evidence observations + current-state view (Plan D D1).

Revision ID: 20260623_0050
Revises: 20260609_0049
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260623_0050"
down_revision: Union[str, Sequence[str], None] = "20260609_0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipment_evidence_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("line_identity_key", sa.String(length=256), nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=256), nullable=False),
        sa.Column("source_row_hash", sa.String(length=40), nullable=False),
        sa.Column("evidence_line_id", sa.Integer(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("source_sheet", sa.String(length=128), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("line_state", sa.String(length=32), nullable=False),
        sa.Column("raw_source_row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("operating_unit", sa.String(length=128), nullable=True),
        sa.Column("bill_to_raw", sa.String(length=512), nullable=True),
        sa.Column("ship_to_raw", sa.String(length=512), nullable=True),
        sa.Column("order_no", sa.String(length=128), nullable=True),
        sa.Column("order_line", sa.String(length=64), nullable=True),
        sa.Column("delivery_no", sa.String(length=128), nullable=True),
        sa.Column("invoice_line", sa.String(length=64), nullable=True),
        sa.Column("item_code", sa.String(length=128), nullable=True),
        sa.Column("sales_model_name", sa.String(length=256), nullable=True),
        sa.Column("customer_item", sa.String(length=256), nullable=True),
        sa.Column("ean_code", sa.String(length=32), nullable=True),
        sa.Column("upc_code", sa.String(length=32), nullable=True),
        sa.Column("mpor_item_no", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("ship_confirm_date", sa.Date(), nullable=True),
        sa.Column("schedule_ship_date", sa.Date(), nullable=True),
        sa.Column("promise_date", sa.Date(), nullable=True),
        sa.Column("exwork_date", sa.Date(), nullable=True),
        sa.Column("erd_date", sa.Date(), nullable=True),
        sa.Column("est_pod_date", sa.Date(), nullable=True),
        sa.Column("pod_date", sa.Date(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_resolution_status", sa.String(length=64), nullable=False),
        sa.Column("product_resolution_token", sa.String(length=512), nullable=True),
        sa.Column("product_resolution_detail", sa.Text(), nullable=True),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("distributor_resolution_status", sa.String(length=64), nullable=False),
        sa.Column("distributor_resolution_token", sa.String(length=512), nullable=True),
        sa.Column("customer_dealer_token", sa.String(length=512), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_resolution_status", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
        sa.ForeignKeyConstraint(["evidence_line_id"], ["shipment_evidence_line.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["shipment_evidence_observation.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_job_id",
            "source_row_hash",
            name="uq_shipment_ev_obs_job_row_hash",
        ),
    )
    op.create_index("ix_shipment_ev_obs_import_job", "shipment_evidence_observation", ["import_job_id"])
    op.create_index("ix_shipment_ev_obs_line_identity", "shipment_evidence_observation", ["line_identity_key"])
    op.create_index("ix_shipment_ev_obs_valid_from", "shipment_evidence_observation", ["valid_from"])
    op.create_index(
        "ix_shipment_ev_obs_product_status",
        "shipment_evidence_observation",
        ["product_resolution_status"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO shipment_evidence_observation (
                line_identity_key,
                import_job_id,
                source_key,
                source_row_hash,
                evidence_line_id,
                valid_from,
                observed_at,
                source_sheet,
                source_row_number,
                report_type,
                line_state,
                raw_source_row,
                operating_unit,
                bill_to_raw,
                ship_to_raw,
                order_no,
                order_line,
                delivery_no,
                invoice_line,
                item_code,
                sales_model_name,
                customer_item,
                ean_code,
                upc_code,
                mpor_item_no,
                quantity,
                unit_price,
                amount,
                currency_code,
                ship_confirm_date,
                schedule_ship_date,
                promise_date,
                exwork_date,
                erd_date,
                est_pod_date,
                pod_date,
                product_id,
                product_resolution_status,
                product_resolution_token,
                product_resolution_detail,
                distributor_id,
                distributor_resolution_status,
                distributor_resolution_token,
                customer_dealer_token,
                customer_id,
                customer_resolution_status
            )
            SELECT
                CASE
                    WHEN NULLIF(btrim(coalesce(sel.order_no, '')), '') IS NOT NULL THEN
                        left(
                            'order:' || concat_ws(
                                '|',
                                nullif(btrim(coalesce(sel.operating_unit, '')), ''),
                                nullif(btrim(coalesce(sel.order_no, '')), ''),
                                nullif(btrim(coalesce(sel.order_line, '')), ''),
                                nullif(btrim(coalesce(sel.item_code, '')), '')
                            ),
                            256
                        )
                    WHEN NULLIF(btrim(coalesce(sel.delivery_no, '')), '') IS NOT NULL
                      OR NULLIF(btrim(coalesce(sel.invoice_line, '')), '') IS NOT NULL THEN
                        left(
                            'ship:' || concat_ws(
                                '|',
                                nullif(btrim(coalesce(sel.operating_unit, '')), ''),
                                nullif(btrim(coalesce(sel.delivery_no, '')), ''),
                                nullif(btrim(coalesce(sel.invoice_line, '')), ''),
                                nullif(btrim(coalesce(sel.item_code, '')), '')
                            ),
                            256
                        )
                    ELSE
                        left('digest:' || substr(md5(sel.raw_source_row::text), 1, 40), 256)
                END AS line_identity_key,
                sel.import_job_id,
                sel.source_key,
                substr(md5(row_to_json(sel)::text), 1, 40) AS source_row_hash,
                sel.id AS evidence_line_id,
                coalesce(ij.completed_at, ij.created_at, sel.created_at) AS valid_from,
                coalesce(ij.created_at, sel.created_at) AS observed_at,
                sel.source_sheet,
                sel.source_row_number,
                sel.report_type,
                sel.line_state,
                sel.raw_source_row,
                sel.operating_unit,
                sel.bill_to_raw,
                sel.ship_to_raw,
                sel.order_no,
                sel.order_line,
                sel.delivery_no,
                sel.invoice_line,
                sel.item_code,
                sel.sales_model_name,
                sel.customer_item,
                sel.ean_code,
                sel.upc_code,
                sel.mpor_item_no,
                sel.quantity,
                sel.unit_price,
                sel.amount,
                sel.currency_code,
                sel.ship_confirm_date,
                sel.schedule_ship_date,
                sel.promise_date,
                sel.exwork_date,
                sel.erd_date,
                sel.est_pod_date,
                sel.pod_date,
                sel.product_id,
                sel.product_resolution_status,
                sel.product_resolution_token,
                sel.product_resolution_detail,
                sel.distributor_id,
                sel.distributor_resolution_status,
                sel.distributor_resolution_token,
                sel.customer_dealer_token,
                sel.customer_id,
                sel.customer_resolution_status
            FROM shipment_evidence_line sel
            JOIN import_job ij ON ij.id = sel.import_job_id
            ON CONFLICT ON CONSTRAINT uq_shipment_ev_obs_job_row_hash DO NOTHING
            """
        )
    )

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


def downgrade() -> None:
    op.execute(sa.text("DROP VIEW IF EXISTS shipment_evidence_current"))
    op.drop_index("ix_shipment_ev_obs_product_status", table_name="shipment_evidence_observation")
    op.drop_index("ix_shipment_ev_obs_valid_from", table_name="shipment_evidence_observation")
    op.drop_index("ix_shipment_ev_obs_line_identity", table_name="shipment_evidence_observation")
    op.drop_index("ix_shipment_ev_obs_import_job", table_name="shipment_evidence_observation")
    op.drop_table("shipment_evidence_observation")
