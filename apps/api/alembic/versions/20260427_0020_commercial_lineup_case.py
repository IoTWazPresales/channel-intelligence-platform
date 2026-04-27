"""Commercial lineup case and line tables.

Revision ID: 20260427_0020
Revises: 20260427_0019
Create Date: 2026-04-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260427_0020"
down_revision: Union[str, Sequence[str], None] = "20260427_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commercial_lineup_case",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=True),
        sa.Column("commercial_plan_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=512), nullable=True),
        sa.Column("period_label", sa.String(length=64), nullable=True),
        sa.Column("country_code", sa.String(length=16), nullable=True),
        sa.Column("currency_code", sa.String(length=16), nullable=True),
        sa.Column("import_intent", sa.String(length=64), nullable=False, server_default="current_working_lineup"),
        sa.Column("source_context", sa.String(length=64), nullable=False, server_default="commercial_planner"),
        sa.Column("commercial_status", sa.String(length=32), nullable=False, server_default="draft_imported"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["commercial_plan_id"], ["commercial_plan.id"]),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commercial_lineup_case_import_job_id", "commercial_lineup_case", ["import_job_id"])
    op.create_index("ix_commercial_lineup_case_commercial_plan_id", "commercial_lineup_case", ["commercial_plan_id"])

    op.create_table(
        "commercial_lineup_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("customer_token", sa.String(length=256), nullable=True),
        sa.Column("sku_raw", sa.String(length=128), nullable=True),
        sa.Column("part_number_raw", sa.String(length=128), nullable=True),
        sa.Column("model_raw", sa.String(length=512), nullable=True),
        sa.Column("base_unit_raw", sa.String(length=128), nullable=True),
        sa.Column("quantity_units", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("month_split_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("msrp_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("promo_price_evidence_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("dap_evidence_local", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("rebate_pct_evidence", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("distributor_margin_pct_evidence", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("vat_pct_evidence", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("diagnostic_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_row_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("row_status", sa.String(length=32), nullable=False, server_default="imported"),
        sa.Column("mapping_confidence", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["commercial_lineup_case.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_commercial_lineup_line_case_id", "commercial_lineup_line", ["case_id"])
    op.create_index("ix_commercial_lineup_line_product_id", "commercial_lineup_line", ["product_id"])
    op.create_index("ix_commercial_lineup_line_customer_id", "commercial_lineup_line", ["customer_id"])
    op.create_index("ix_commercial_lineup_line_distributor_id", "commercial_lineup_line", ["distributor_id"])


def downgrade() -> None:
    op.drop_index("ix_commercial_lineup_line_distributor_id", table_name="commercial_lineup_line")
    op.drop_index("ix_commercial_lineup_line_customer_id", table_name="commercial_lineup_line")
    op.drop_index("ix_commercial_lineup_line_product_id", table_name="commercial_lineup_line")
    op.drop_index("ix_commercial_lineup_line_case_id", table_name="commercial_lineup_line")
    op.drop_table("commercial_lineup_line")
    op.drop_index("ix_commercial_lineup_case_commercial_plan_id", table_name="commercial_lineup_case")
    op.drop_index("ix_commercial_lineup_case_import_job_id", table_name="commercial_lineup_case")
    op.drop_table("commercial_lineup_case")
