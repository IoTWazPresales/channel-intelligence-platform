"""CPOR U4.5 CST D1 surface + case_name + line USD totals (Warren-approved Phase A).

Revision ID: 20260709_0068
Revises: 20260708_0067

Approved amendments:
- cpor_case.case_name
- cpor_case_line.ttl_support_usd / ttl_result_usd (recompute-owned; no builder math)
- CST: site_label / unit_mac / vat_basis on fact+staging; article alias; feed_profile_json;
  dim_customer.is_key_account; report slots; listing seed
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260709_0068"
down_revision: Union[str, Sequence[str], None] = "20260708_0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- CPOR case / line amendments (export headers + recompute) ---
    op.add_column("cpor_case", sa.Column("case_name", sa.String(length=256), nullable=True))
    op.add_column(
        "cpor_case_line",
        sa.Column("ttl_support_usd", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "cpor_case_line",
        sa.Column("ttl_result_usd", sa.Numeric(18, 4), nullable=True),
    )

    # --- dim_customer key-account ---
    op.add_column(
        "dim_customer",
        sa.Column(
            "is_key_account",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # --- fact_customer_sellthrough D1 columns ---
    op.add_column(
        "fact_customer_sellthrough",
        sa.Column("site_label", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "fact_customer_sellthrough",
        sa.Column("unit_mac", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "fact_customer_sellthrough",
        sa.Column("vat_basis", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_fact_customer_sellthrough_customer_site_period",
        "fact_customer_sellthrough",
        ["customer_id", "site_label", "period_start_date"],
        postgresql_where=sa.text("site_label IS NOT NULL"),
    )

    # --- staging D1 columns ---
    op.add_column(
        "import_customer_sellthrough_staging_line",
        sa.Column("site_label", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "import_customer_sellthrough_staging_line",
        sa.Column("unit_mac", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "import_customer_sellthrough_staging_line",
        sa.Column("vat_basis", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "import_customer_sellthrough_staging_line",
        sa.Column("raw_article_token", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "import_customer_sellthrough_staging_line",
        sa.Column("listing_external_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "import_customer_sellthrough_staging_line",
        sa.Column("listing_marketplace", sa.String(length=32), nullable=True),
    )

    # --- feed profile on existing config ---
    op.add_column(
        "customer_report_config",
        sa.Column("feed_profile_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # --- customer_article_alias ---
    op.create_table(
        "customer_article_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("article_no_normalized", sa.String(length=256), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "article_no_normalized",
            name="uq_customer_article_alias_customer_article",
        ),
    )
    op.create_index("ix_customer_article_alias_customer_id", "customer_article_alias", ["customer_id"])
    op.create_index("ix_customer_article_alias_product_id", "customer_article_alias", ["product_id"])

    # --- expected-report slots ---
    op.create_table(
        "customer_cst_report_slot",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="due"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_job_id", sa.Integer(), nullable=True),
        sa.Column("cadence_snapshot", sa.String(length=16), nullable=True),
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
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "week_start_date",
            name="uq_customer_cst_report_slot_customer_week",
        ),
    )
    op.create_index(
        "ix_customer_cst_report_slot_customer_id",
        "customer_cst_report_slot",
        ["customer_id"],
    )

    # --- listing seed (LC-U1 handoff; no registry) ---
    op.create_table(
        "cst_listing_seed",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="proposed"),
        sa.Column("import_job_id", sa.Integer(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "customer_id",
            "marketplace",
            "external_id",
            name="uq_cst_listing_seed_customer_marketplace_external",
        ),
    )
    op.create_index("ix_cst_listing_seed_customer_id", "cst_listing_seed", ["customer_id"])
    op.create_index("ix_cst_listing_seed_product_id", "cst_listing_seed", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_cst_listing_seed_product_id", table_name="cst_listing_seed")
    op.drop_index("ix_cst_listing_seed_customer_id", table_name="cst_listing_seed")
    op.drop_table("cst_listing_seed")

    op.drop_index("ix_customer_cst_report_slot_customer_id", table_name="customer_cst_report_slot")
    op.drop_table("customer_cst_report_slot")

    op.drop_index("ix_customer_article_alias_product_id", table_name="customer_article_alias")
    op.drop_index("ix_customer_article_alias_customer_id", table_name="customer_article_alias")
    op.drop_table("customer_article_alias")

    op.drop_column("customer_report_config", "feed_profile_json")

    op.drop_column("import_customer_sellthrough_staging_line", "listing_marketplace")
    op.drop_column("import_customer_sellthrough_staging_line", "listing_external_id")
    op.drop_column("import_customer_sellthrough_staging_line", "raw_article_token")
    op.drop_column("import_customer_sellthrough_staging_line", "vat_basis")
    op.drop_column("import_customer_sellthrough_staging_line", "unit_mac")
    op.drop_column("import_customer_sellthrough_staging_line", "site_label")

    op.drop_index(
        "ix_fact_customer_sellthrough_customer_site_period",
        table_name="fact_customer_sellthrough",
    )
    op.drop_column("fact_customer_sellthrough", "vat_basis")
    op.drop_column("fact_customer_sellthrough", "unit_mac")
    op.drop_column("fact_customer_sellthrough", "site_label")

    op.drop_column("dim_customer", "is_key_account")

    op.drop_column("cpor_case_line", "ttl_result_usd")
    op.drop_column("cpor_case_line", "ttl_support_usd")
    op.drop_column("cpor_case", "case_name")
