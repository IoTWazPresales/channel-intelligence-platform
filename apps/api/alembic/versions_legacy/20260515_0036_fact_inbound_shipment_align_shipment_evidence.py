"""Widen fact_inbound_shipment to mirror shipment evidence (truth layer).

Revision ID: 20260515_0036
Revises: 20260513_0035

- Nullable product_id, eta_date, quantity for parity with ShipmentEvidenceLine.
- Lineage: import_job_id, source_key (UNIQUE global upsert), shipment_evidence_line_id (SET NULL on line delete).
- Full logistics, measures, seven dates, resolution fields, raw_source_row, line_state (new) + status (kept).
- Backfill source_key = 'legacy:' || id for existing rows before NOT NULL + UNIQUE.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260515_0036"
down_revision: Union[str, Sequence[str], None] = "20260513_0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fact_inbound_shipment", sa.Column("source_key", sa.String(length=256), nullable=True))
    op.execute(
        sa.text(
            "UPDATE fact_inbound_shipment SET source_key = 'legacy:{' || id::text || '}' "
            "WHERE source_key IS NULL"
        )
    )
    op.alter_column(
        "fact_inbound_shipment",
        "product_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "fact_inbound_shipment",
        "eta_date",
        existing_type=sa.Date(),
        nullable=True,
    )
    op.alter_column(
        "fact_inbound_shipment",
        "quantity",
        existing_type=sa.Numeric(18, 4),
        nullable=True,
    )

    op.add_column("fact_inbound_shipment", sa.Column("import_job_id", sa.Integer(), nullable=True))
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("shipment_evidence_line_id", sa.Integer(), nullable=True),
    )
    op.add_column("fact_inbound_shipment", sa.Column("source_sheet", sa.String(length=128), nullable=True))
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("source_row_number", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("report_type", sa.String(length=64), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("line_state", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "fact_inbound_shipment",
        sa.Column(
            "raw_source_row",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("fact_inbound_shipment", sa.Column("operating_unit", sa.String(length=128), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("bill_to_raw", sa.String(length=512), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("ship_to_raw", sa.String(length=512), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("order_no", sa.String(length=128), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("order_line", sa.String(length=64), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("delivery_no", sa.String(length=128), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("invoice_line", sa.String(length=64), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("item_code", sa.String(length=128), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("sales_model_name", sa.String(length=256), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("customer_item", sa.String(length=256), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("ean_code", sa.String(length=32), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("upc_code", sa.String(length=32), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("mpor_item_no", sa.String(length=128), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("unit_price", sa.Numeric(18, 4), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("amount", sa.Numeric(18, 4), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("currency_code", sa.String(length=8), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("ship_confirm_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("schedule_ship_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("promise_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("exwork_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("erd_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("est_pod_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("pod_date", sa.Date(), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("customer_id", sa.Integer(), nullable=True))
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("product_resolution_status", sa.String(length=64), nullable=False, server_default="unknown"),
    )
    op.add_column("fact_inbound_shipment", sa.Column("product_resolution_token", sa.String(length=512), nullable=True))
    op.add_column("fact_inbound_shipment", sa.Column("product_resolution_detail", sa.Text(), nullable=True))
    op.add_column(
        "fact_inbound_shipment",
        sa.Column(
            "distributor_resolution_status",
            sa.String(length=64),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("distributor_resolution_token", sa.String(length=512), nullable=True),
    )
    op.add_column("fact_inbound_shipment", sa.Column("customer_dealer_token", sa.String(length=512), nullable=True))
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("customer_resolution_status", sa.String(length=64), nullable=True),
    )

    op.alter_column("fact_inbound_shipment", "source_key", nullable=False)
    op.create_unique_constraint(
        "uq_fact_inbound_shipment_source_key",
        "fact_inbound_shipment",
        ["source_key"],
    )

    op.create_foreign_key(
        "fk_fact_inbound_shipment_import_job_id",
        "fact_inbound_shipment",
        "import_job",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_fact_inbound_shipment_shipment_evidence_line_id",
        "fact_inbound_shipment",
        "shipment_evidence_line",
        ["shipment_evidence_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_fact_inbound_shipment_customer_id",
        "fact_inbound_shipment",
        "dim_customer",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_fact_inbound_shipment_import_job_id",
        "fact_inbound_shipment",
        ["import_job_id"],
    )

    op.alter_column("fact_inbound_shipment", "source_row_number", server_default=None)
    op.alter_column("fact_inbound_shipment", "report_type", server_default=None)
    op.alter_column("fact_inbound_shipment", "line_state", server_default=None)
    op.alter_column("fact_inbound_shipment", "raw_source_row", server_default=None)
    op.alter_column("fact_inbound_shipment", "product_resolution_status", server_default=None)
    op.alter_column("fact_inbound_shipment", "distributor_resolution_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_fact_inbound_shipment_import_job_id", table_name="fact_inbound_shipment")
    op.drop_constraint("fk_fact_inbound_shipment_customer_id", "fact_inbound_shipment", type_="foreignkey")
    op.drop_constraint(
        "fk_fact_inbound_shipment_shipment_evidence_line_id",
        "fact_inbound_shipment",
        type_="foreignkey",
    )
    op.drop_constraint("fk_fact_inbound_shipment_import_job_id", "fact_inbound_shipment", type_="foreignkey")
    op.drop_constraint("uq_fact_inbound_shipment_source_key", "fact_inbound_shipment", type_="unique")

    op.drop_column("fact_inbound_shipment", "customer_resolution_status")
    op.drop_column("fact_inbound_shipment", "customer_dealer_token")
    op.drop_column("fact_inbound_shipment", "distributor_resolution_token")
    op.drop_column("fact_inbound_shipment", "distributor_resolution_status")
    op.drop_column("fact_inbound_shipment", "product_resolution_detail")
    op.drop_column("fact_inbound_shipment", "product_resolution_token")
    op.drop_column("fact_inbound_shipment", "product_resolution_status")
    op.drop_column("fact_inbound_shipment", "customer_id")
    op.drop_column("fact_inbound_shipment", "pod_date")
    op.drop_column("fact_inbound_shipment", "est_pod_date")
    op.drop_column("fact_inbound_shipment", "erd_date")
    op.drop_column("fact_inbound_shipment", "exwork_date")
    op.drop_column("fact_inbound_shipment", "promise_date")
    op.drop_column("fact_inbound_shipment", "schedule_ship_date")
    op.drop_column("fact_inbound_shipment", "ship_confirm_date")
    op.drop_column("fact_inbound_shipment", "currency_code")
    op.drop_column("fact_inbound_shipment", "amount")
    op.drop_column("fact_inbound_shipment", "unit_price")
    op.drop_column("fact_inbound_shipment", "mpor_item_no")
    op.drop_column("fact_inbound_shipment", "upc_code")
    op.drop_column("fact_inbound_shipment", "ean_code")
    op.drop_column("fact_inbound_shipment", "customer_item")
    op.drop_column("fact_inbound_shipment", "sales_model_name")
    op.drop_column("fact_inbound_shipment", "item_code")
    op.drop_column("fact_inbound_shipment", "invoice_line")
    op.drop_column("fact_inbound_shipment", "delivery_no")
    op.drop_column("fact_inbound_shipment", "order_line")
    op.drop_column("fact_inbound_shipment", "order_no")
    op.drop_column("fact_inbound_shipment", "ship_to_raw")
    op.drop_column("fact_inbound_shipment", "bill_to_raw")
    op.drop_column("fact_inbound_shipment", "operating_unit")
    op.drop_column("fact_inbound_shipment", "raw_source_row")
    op.drop_column("fact_inbound_shipment", "line_state")
    op.drop_column("fact_inbound_shipment", "report_type")
    op.drop_column("fact_inbound_shipment", "source_row_number")
    op.drop_column("fact_inbound_shipment", "source_sheet")
    op.drop_column("fact_inbound_shipment", "shipment_evidence_line_id")
    op.drop_column("fact_inbound_shipment", "import_job_id")
    op.drop_column("fact_inbound_shipment", "source_key")

    op.execute(sa.text("UPDATE fact_inbound_shipment SET quantity = 0 WHERE quantity IS NULL"))
    op.execute(sa.text("UPDATE fact_inbound_shipment SET eta_date = CURRENT_DATE WHERE eta_date IS NULL"))
    op.execute(sa.text("DELETE FROM fact_inbound_shipment WHERE product_id IS NULL"))
    op.alter_column("fact_inbound_shipment", "quantity", existing_type=sa.Numeric(18, 4), nullable=False)
    op.alter_column("fact_inbound_shipment", "eta_date", existing_type=sa.Date(), nullable=False)
    op.alter_column("fact_inbound_shipment", "product_id", existing_type=sa.Integer(), nullable=False)
