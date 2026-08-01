"""Shipment / inbound evidence: canonical lines per import job.

Revision ID: 20260507_0030
Revises: 20260507_0029
Create Date: 2026-05-07
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260507_0030"
down_revision: Union[str, Sequence[str], None] = "20260507_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipment_evidence_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=False),
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
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_resolution_status", sa.String(length=64), nullable=False),
        sa.Column("product_resolution_token", sa.String(length=512), nullable=True),
        sa.Column("product_resolution_detail", sa.Text(), nullable=True),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("distributor_resolution_status", sa.String(length=64), nullable=False),
        sa.Column("distributor_resolution_token", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shipment_evidence_line_import_job", "shipment_evidence_line", ["import_job_id"])
    op.create_index("ix_shipment_evidence_line_line_state", "shipment_evidence_line", ["line_state"])
    op.create_index("ix_shipment_evidence_line_report_type", "shipment_evidence_line", ["report_type"])
    op.create_index("ix_shipment_evidence_line_product_status", "shipment_evidence_line", ["product_resolution_status"])

    op.execute(
        sa.text(
            "UPDATE import_template SET pipeline_handler = 'shipment_evidence_import' "
            "WHERE slug = 'inbound_shipments'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE import_template SET pipeline_handler = 'stub_noop' "
            "WHERE slug = 'inbound_shipments' AND pipeline_handler = 'shipment_evidence_import'"
        )
    )

    op.drop_index("ix_shipment_evidence_line_product_status", table_name="shipment_evidence_line")
    op.drop_index("ix_shipment_evidence_line_report_type", table_name="shipment_evidence_line")
    op.drop_index("ix_shipment_evidence_line_line_state", table_name="shipment_evidence_line")
    op.drop_index("ix_shipment_evidence_line_import_job", table_name="shipment_evidence_line")
    op.drop_table("shipment_evidence_line")
