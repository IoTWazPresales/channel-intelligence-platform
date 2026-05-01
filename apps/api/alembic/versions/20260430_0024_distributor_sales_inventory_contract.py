"""Distributor sales & inventory import: fact extensions, staging, candidates, customer aliases.

Revision ID: 20260430_0024
Revises: 20260430_0023
Create Date: 2026-04-30
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

revision: str = "20260430_0024"
down_revision: Union[str, Sequence[str], None] = "20260430_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fact_sales_sellout",
        sa.Column("unit_sellout_price_ex_tax_amount", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "fact_sales_sellout",
        sa.Column("reported_revenue_amount", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "fact_sales_sellout",
        sa.Column("computed_revenue_amount", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column("fact_sales_sellout", sa.Column("currency_code", sa.String(length=8), nullable=True))
    op.add_column("fact_sales_sellout", sa.Column("source_import_job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_fact_sales_sellout_source_import_job_id_import_job",
        "fact_sales_sellout",
        "import_job",
        ["source_import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "fact_inventory_distributor",
        sa.Column("source_import_job_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_fact_inventory_distributor_source_import_job_id_import_job",
        "fact_inventory_distributor",
        "import_job",
        ["source_import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "import_distributor_si_staging_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("raw_row_payload", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mapped_canonical", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_distributor_token", sa.String(length=512), nullable=True),
        sa.Column("raw_customer_dealer_token", sa.String(length=512), nullable=True),
        sa.Column("raw_dealer_group_token", sa.String(length=512), nullable=True),
        sa.Column("raw_product_token", sa.String(length=512), nullable=True),
        sa.Column("resolved_distributor_id", sa.Integer(), nullable=True),
        sa.Column("resolved_customer_id", sa.Integer(), nullable=True),
        sa.Column("resolved_product_id", sa.Integer(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=True),
        sa.Column("quantity_sold", sa.Numeric(18, 4), nullable=True),
        sa.Column("stock_on_hand", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit_sellout_price_ex_tax_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("reported_revenue_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("computed_revenue_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=True),
        sa.Column("resolution_status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("diagnostic_codes", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("apply_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("fact_sellout_row_id", sa.Integer(), nullable=True),
        sa.Column("fact_inventory_row_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_distributor_id"], ["dim_distributor.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_customer_id"], ["dim_customer.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_product_id"], ["dim_product.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_distributor_si_staging_line_job_row",
        "import_distributor_si_staging_line",
        ["import_job_id", "source_row_number"],
        unique=True,
    )
    op.create_index("ix_import_distributor_si_staging_line_job", "import_distributor_si_staging_line", ["import_job_id"])

    op.create_table(
        "import_entity_mapping_candidate",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=False),
        sa.Column("source_definition_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("normalized_key", sa.String(length=512), nullable=False),
        sa.Column("dealer_group_token", sa.String(length=512), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_units", sa.Numeric(18, 4), nullable=True),
        sa.Column("total_reported_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("sample_raw_values", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("suggested_entity_id", sa.Integer(), nullable=True),
        sa.Column("match_reason", sa.String(length=256), nullable=True),
        sa.Column("confidence_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="needs_review"),
        sa.Column("context", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_definition_id"], ["source_definition.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_job_id",
            "entity_type",
            "normalized_key",
            name="uq_import_entity_mapping_candidate_job_entity_key",
        ),
    )
    op.create_index("ix_import_entity_mapping_candidate_job", "import_entity_mapping_candidate", ["import_job_id"])

    op.create_table(
        "customer_source_token_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("source_definition_id", sa.Integer(), nullable=True),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("raw_token", sa.String(length=512), nullable=False),
        sa.Column("normalized_token", sa.String(length=512), nullable=False),
        sa.Column("dealer_group_token", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="approved"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_definition_id"], ["source_definition.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_source_token_alias_norm", "customer_source_token_alias", ["normalized_token"])

    row = next(t for t in IMPORT_TEMPLATE_ROWS if t["slug"] == "distributor_inventory")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE import_template
            SET display_name = :display_name,
                description = :description,
                pipeline_handler = :pipeline_handler,
                expected_columns = CAST(:expected_columns AS jsonb),
                destructive_apply_requires_confirm = true,
                updated_at = now()
            WHERE slug = 'distributor_inventory'
            """
        ),
        {
            "display_name": row["display_name"],
            "description": row["description"],
            "pipeline_handler": row["pipeline_handler"],
            "expected_columns": json.dumps(row["expected_columns"]),
        },
    )


def downgrade() -> None:
    op.drop_index("ix_customer_source_token_alias_norm", table_name="customer_source_token_alias")
    op.drop_table("customer_source_token_alias")

    op.drop_index("ix_import_entity_mapping_candidate_job", table_name="import_entity_mapping_candidate")
    op.drop_table("import_entity_mapping_candidate")

    op.drop_index("ix_import_distributor_si_staging_line_job", table_name="import_distributor_si_staging_line")
    op.drop_index("ix_import_distributor_si_staging_line_job_row", table_name="import_distributor_si_staging_line")
    op.drop_table("import_distributor_si_staging_line")

    op.drop_constraint(
        "fk_fact_inventory_distributor_source_import_job_id_import_job",
        "fact_inventory_distributor",
        type_="foreignkey",
    )
    op.drop_column("fact_inventory_distributor", "source_import_job_id")

    op.drop_constraint(
        "fk_fact_sales_sellout_source_import_job_id_import_job",
        "fact_sales_sellout",
        type_="foreignkey",
    )
    op.drop_column("fact_sales_sellout", "source_import_job_id")
    op.drop_column("fact_sales_sellout", "currency_code")
    op.drop_column("fact_sales_sellout", "computed_revenue_amount")
    op.drop_column("fact_sales_sellout", "reported_revenue_amount")
    op.drop_column("fact_sales_sellout", "unit_sellout_price_ex_tax_amount")
