"""Historical lineup import foundation tables and template seed.

Revision ID: 20260427_0019
Revises: 20260427_0018
Create Date: 2026-04-27
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260427_0019"
down_revision: Union[str, Sequence[str], None] = "20260427_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historical_lineup_import_header",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("workbook_name", sa.String(length=512), nullable=False),
        sa.Column("sheet_name", sa.String(length=256), nullable=False),
        sa.Column("pm_domain", sa.String(length=64), nullable=True),
        sa.Column("period_label", sa.String(length=64), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("country_code", sa.String(length=16), nullable=True),
        sa.Column("currency_code", sa.String(length=16), nullable=True),
        sa.Column("source_metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["dim_channel.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_definition.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_historical_lineup_import_header_import_job_id", "historical_lineup_import_header", ["import_job_id"])
    op.create_index("ix_historical_lineup_import_header_source_id", "historical_lineup_import_header", ["source_id"])

    op.create_table(
        "historical_lineup_import_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("header_id", sa.Integer(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("sku_raw", sa.String(length=128), nullable=True),
        sa.Column("part_number_raw", sa.String(length=128), nullable=True),
        sa.Column("model_raw", sa.String(length=512), nullable=True),
        sa.Column("base_unit_raw", sa.String(length=128), nullable=True),
        sa.Column("msrp_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("promo_price_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("quantity_units", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("month_split_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dap_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("actual_dap_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("disti_cost_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("disti_margin_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("rebate_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("dealer_margin_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("vat_pct", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("customer_feedback", sa.Text(), nullable=True),
        sa.Column("workflow_notes", sa.Text(), nullable=True),
        sa.Column("row_status", sa.String(length=32), nullable=False),
        sa.Column("mapping_confidence", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("diagnostic_codes", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_row_payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["header_id"], ["historical_lineup_import_header.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_historical_lineup_import_line_header_id", "historical_lineup_import_line", ["header_id"])

    conn = op.get_bind()
    expected_columns = {
        "customer_token": {"aliases": ["customer", "account_name", "customer_code"], "required": False},
        "distributor_token": {"aliases": ["distributor", "disti", "distributor_code"], "required": False},
        "sku_raw": {"aliases": ["sku", "item", "product_sku"], "required": False},
        "quantity_units": {"aliases": ["qty", "quantity", "units"], "required": False},
        "period_label": {"aliases": ["period", "month", "quarter"], "required": False},
    }
    conn.execute(
        sa.text(
            """
            INSERT INTO import_template (
                slug, display_name, description, enabled, hidden, admin_only,
                requires_provider, pipeline_handler, destructive_apply_requires_confirm,
                accepted_file_types, expected_columns
            )
            VALUES (
                'historical_lineup',
                'Historical lineup workbook',
                'Workbook-style historical lineups with governed parsing, diagnostics, and normalized history persistence.',
                true,
                false,
                true,
                true,
                'historical_lineup_workbook',
                false,
                CAST(:accepted_file_types AS jsonb),
                CAST(:expected_columns AS jsonb)
            )
            ON CONFLICT (slug) DO NOTHING
            """
        ),
        {
            "accepted_file_types": json.dumps([".csv", ".xlsx", ".xlsm"]),
            "expected_columns": json.dumps(expected_columns),
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO source_definition (
                import_template_id, code, name, source_kind, expected_template, parser_module, is_active
            )
            SELECT it.id, 'historical_lineup_default', 'Default historical lineup feed', 'planning_extract',
                   CAST(NULL AS jsonb), CAST(NULL AS varchar(256)), true
            FROM import_template it
            WHERE it.slug = 'historical_lineup'
              AND NOT EXISTS (SELECT 1 FROM source_definition s WHERE s.code = 'historical_lineup_default')
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM source_definition WHERE code = 'historical_lineup_default'"))
    conn.execute(sa.text("DELETE FROM import_template WHERE slug = 'historical_lineup'"))
    op.drop_index("ix_historical_lineup_import_line_header_id", table_name="historical_lineup_import_line")
    op.drop_table("historical_lineup_import_line")
    op.drop_index("ix_historical_lineup_import_header_source_id", table_name="historical_lineup_import_header")
    op.drop_index("ix_historical_lineup_import_header_import_job_id", table_name="historical_lineup_import_header")
    op.drop_table("historical_lineup_import_header")
