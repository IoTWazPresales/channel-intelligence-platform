"""Customer sell-through staging, report config, and import template seed.

Revision ID: 20260518_0045
Revises: 20260518_0044
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table, unique_constraint_exists

revision: str = "20260518_0045"
down_revision: Union[str, Sequence[str], None] = "20260518_0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CUSTOMER_SELL_THROUGH_EXPECTED_COLUMNS = {
    "units_sold": {
        "aliases": [
            "units_sold",
            "qty_sold",
            "quantity_sold",
            "tw_sales",
            "tw sales",
            "sales",
            "units",
            "qty",
        ],
        "required": True,
    },
    "product_identifier": {
        "aliases": [
            "product_code",
            "sku",
            "item_code",
            "itemno",
            "article",
            "barcode",
            "supplier_code",
        ],
        "required": True,
    },
    "location_token": {
        "aliases": [
            "site_code",
            "site_name",
            "store_code",
            "store_name",
            "site",
        ],
        "required": False,
    },
    "period_ref": {
        "aliases": [
            "week",
            "transaction_week",
            "period",
            "report_week",
            "week_no",
        ],
        "required": False,
    },
    "unit_sell_price": {
        "aliases": [
            "sell_price",
            "unit_price",
            "price",
            "selling_price",
            "retail_price",
        ],
        "required": False,
    },
    "unit_cost": {
        "aliases": [
            "cost",
            "unit_cost",
            "mac",
            "moving_avg_cost",
            "cost_price",
        ],
        "required": False,
    },
    "reported_soh": {
        "aliases": [
            "soh",
            "stock_on_hand",
            "in_stock",
            "qty_available",
            "current_stock",
            "on_hand",
            "total_soh",
            "total_sellable_soh",
        ],
        "required": False,
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "import_customer_sellthrough_staging_line"):
        op.create_table(
            "import_customer_sellthrough_staging_line",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("import_job_id", sa.Integer(), nullable=False),
            sa.Column("source_row_number", sa.Integer(), nullable=False),
            sa.Column("raw_row_payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("raw_customer_token", sa.String(length=256), nullable=True),
            sa.Column("raw_location_token", sa.String(length=256), nullable=True),
            sa.Column("raw_product_token", sa.String(length=256), nullable=True),
            sa.Column("raw_period_ref", sa.String(length=64), nullable=True),
            sa.Column("resolved_customer_id", sa.Integer(), nullable=True),
            sa.Column("resolved_location_id", sa.Integer(), nullable=True),
            sa.Column("resolved_product_id", sa.Integer(), nullable=True),
            sa.Column("period_start_date", sa.Date(), nullable=True),
            sa.Column("period_type", sa.String(length=8), nullable=True),
            sa.Column("units_sold", sa.Numeric(18, 4), nullable=True),
            sa.Column("raw_mtd_units", sa.Numeric(18, 4), nullable=True),
            sa.Column(
                "is_mtd_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("unit_sell_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("reported_soh", sa.Numeric(18, 4), nullable=True),
            sa.Column(
                "resolution_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("apply_status", sa.String(length=32), nullable=True),
            sa.Column("fact_sellthrough_row_id", sa.Integer(), nullable=True),
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
            sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["resolved_customer_id"], ["dim_customer.id"]),
            sa.ForeignKeyConstraint(["resolved_location_id"], ["customer_location.id"]),
            sa.ForeignKeyConstraint(["resolved_product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(
                ["fact_sellthrough_row_id"],
                ["fact_customer_sellthrough.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    insp = get_inspector(bind)
    if not has_index(insp, "import_customer_sellthrough_staging_line", "ix_cst_staging_job"):
        op.create_index(
            "ix_cst_staging_job",
            "import_customer_sellthrough_staging_line",
            ["import_job_id"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "import_customer_sellthrough_staging_line", "ix_cst_staging_job_status"):
        op.create_index(
            "ix_cst_staging_job_status",
            "import_customer_sellthrough_staging_line",
            ["import_job_id", "resolution_status"],
        )

    insp = get_inspector(bind)
    if not has_table(insp, "customer_report_config"):
        op.create_table(
            "customer_report_config",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column(
                "reports_expected",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "expected_cadence",
                sa.String(length=16),
                nullable=False,
                server_default="weekly",
            ),
            sa.Column("report_structure_type", sa.String(length=16), nullable=True),
            sa.Column("last_report_received", sa.Date(), nullable=True),
            sa.Column(
                "overdue_threshold_days",
                sa.Integer(),
                nullable=False,
                server_default="10",
            ),
            sa.Column("notes", sa.String(length=512), nullable=True),
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
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "customer_report_config", "uq_customer_report_config_customer_id"):
        op.create_unique_constraint(
            "uq_customer_report_config_customer_id",
            "customer_report_config",
            ["customer_id"],
        )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO import_template (
                slug, display_name, description, enabled, hidden, admin_only,
                requires_provider, pipeline_handler, destructive_apply_requires_confirm,
                accepted_file_types, expected_columns
            ) VALUES (
                :slug, :display_name, :description, :enabled, :hidden, :admin_only,
                :requires_provider, :pipeline_handler, :destructive,
                CAST(:accepted AS jsonb), CAST(:expected AS jsonb)
            )
            ON CONFLICT (slug) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                enabled = EXCLUDED.enabled,
                hidden = EXCLUDED.hidden,
                admin_only = EXCLUDED.admin_only,
                requires_provider = EXCLUDED.requires_provider,
                pipeline_handler = EXCLUDED.pipeline_handler,
                destructive_apply_requires_confirm = EXCLUDED.destructive_apply_requires_confirm,
                accepted_file_types = EXCLUDED.accepted_file_types,
                expected_columns = EXCLUDED.expected_columns
            """
        ),
        {
            "slug": "customer_sell_through",
            "display_name": "Customer Sell-Through Report",
            "description": (
                "Retailer sell-through reports (weekly/monthly file extracts; daily via API in a future phase). "
                "Supports flat, pivoted, multi-sheet, MTD delta, and wide extract layouts."
            ),
            "enabled": True,
            "hidden": False,
            "admin_only": False,
            "requires_provider": True,
            "pipeline_handler": "customer_sell_through",
            "destructive": False,
            "accepted": json.dumps([".csv", ".xlsx", ".xlsm"]),
            "expected": json.dumps(_CUSTOMER_SELL_THROUGH_EXPECTED_COLUMNS),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM import_template WHERE slug = 'customer_sell_through'"))
    insp = get_inspector(bind)
    if has_table(insp, "customer_report_config"):
        op.drop_table("customer_report_config")
    if has_table(insp, "import_customer_sellthrough_staging_line"):
        op.drop_table("import_customer_sellthrough_staging_line")
