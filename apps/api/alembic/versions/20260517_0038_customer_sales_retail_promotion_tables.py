"""Channel Intelligence Phase 1: customer sales, store, retailer listing, promotion product tables.

Revision ID: 20260517_0038
Revises: 20260517_0037
Create Date: 2026-05-17

New tables: dim_store, customer_product_alias, fact_customer_sales,
dim_retailer_listing, fact_promotion_product.
ALTER dim_promotion: add week/year/type/status/notes_extended columns.

DDL is guarded so empty-database upgrades do not fail on duplicates.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_column, has_table

revision: str = "20260517_0038"
down_revision: Union[str, Sequence[str], None] = "20260517_0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    # ── dim_store ──────────────────────────────────────────────────────────────
    if not has_table(insp, "dim_store"):
        op.create_table(
            "dim_store",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("store_code", sa.String(length=64), nullable=False),
            sa.Column("store_name", sa.String(length=256), nullable=True),
            sa.Column("city", sa.String(length=128), nullable=True),
            sa.Column("region_id", sa.Integer(), nullable=True),
            sa.Column("store_type", sa.String(length=32), server_default="standard", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.ForeignKeyConstraint(["region_id"], ["dim_region.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("customer_id", "store_code", name="uq_dim_store_customer_store_code"),
        )
        op.create_index("ix_dim_store_customer_id", "dim_store", ["customer_id"])

    # ── customer_product_alias ─────────────────────────────────────────────────
    insp = get_inspector(bind)
    if not has_table(insp, "customer_product_alias"):
        op.create_table(
            "customer_product_alias",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("source_article_code", sa.String(length=512), nullable=False),
            sa.Column("normalized_code", sa.String(length=512), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), server_default="approved", nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_from_import_job_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_from_import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "customer_id", "normalized_code", name="uq_customer_product_alias_customer_normalized"
            ),
        )
        op.create_index("ix_customer_product_alias_customer_id", "customer_product_alias", ["customer_id"])
        op.create_index("ix_customer_product_alias_product_id", "customer_product_alias", ["product_id"])

    # ── fact_customer_sales ────────────────────────────────────────────────────
    insp = get_inspector(bind)
    if not has_table(insp, "fact_customer_sales"):
        op.create_table(
            "fact_customer_sales",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_key", sa.String(length=256), nullable=False, unique=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=True),
            sa.Column("store_id", sa.Integer(), nullable=True),
            sa.Column("import_job_id", sa.Integer(), nullable=True),
            sa.Column("report_week", sa.Integer(), nullable=True),
            sa.Column("report_year", sa.Integer(), nullable=True),
            sa.Column("report_period", sa.String(length=32), nullable=True),
            sa.Column("transaction_date", sa.Date(), nullable=True),
            sa.Column("quantity_sold", sa.Numeric(18, 4), nullable=True),
            sa.Column("quantity_returned", sa.Numeric(18, 4), nullable=True),
            sa.Column("selling_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("cost_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("currency_code", sa.String(length=8), nullable=True),
            sa.Column("channel_type", sa.String(length=32), nullable=True),
            sa.Column("reported_soh", sa.Numeric(18, 4), nullable=True),
            sa.Column("source_article_code", sa.String(length=512), nullable=True),
            sa.Column("source_store_code", sa.String(length=128), nullable=True),
            sa.Column("product_resolution_status", sa.String(length=64), server_default="no_match", nullable=False),
            sa.Column("store_resolution_status", sa.String(length=64), server_default="no_match", nullable=False),
            sa.Column(
                "raw_source_row",
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'::jsonb"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(["store_id"], ["dim_store.id"]),
            sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_fact_customer_sales_customer_id", "fact_customer_sales", ["customer_id"])
        op.create_index("ix_fact_customer_sales_product_id", "fact_customer_sales", ["product_id"])
        op.create_index("ix_fact_customer_sales_import_job_id", "fact_customer_sales", ["import_job_id"])
        op.create_index(
            "ix_fact_customer_sales_report_period", "fact_customer_sales", ["report_year", "report_week"]
        )

    # ── dim_retailer_listing ───────────────────────────────────────────────────
    insp = get_inspector(bind)
    if not has_table(insp, "dim_retailer_listing"):
        op.create_table(
            "dim_retailer_listing",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("listing_url", sa.String(length=1024), nullable=False),
            sa.Column("retailer_sku", sa.String(length=256), nullable=True),
            sa.Column("expected_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("listing_status", sa.String(length=32), server_default="active", nullable=False),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_price_seen", sa.Numeric(18, 4), nullable=True),
            sa.Column("last_availability_seen", sa.String(length=32), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "product_id", "customer_id", "listing_url", name="uq_retailer_listing_product_customer_url"
            ),
        )

    # ── fact_promotion_product ─────────────────────────────────────────────────
    insp = get_inspector(bind)
    if not has_table(insp, "fact_promotion_product"):
        op.create_table(
            "fact_promotion_product",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("promotion_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("distributor_id", sa.Integer(), nullable=True),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("expected_uplift_pct", sa.Numeric(6, 2), nullable=True),
            sa.Column("target_quantity", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(["promotion_id"], ["dim_promotion.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_unique_constraint(
            "uq_fact_promotion_product_composite",
            "fact_promotion_product",
            ["promotion_id", "product_id"],
        )
        op.execute(
            sa.text(
                """
                DROP CONSTRAINT IF EXISTS uq_fact_promotion_product_composite;
                """
            )
        ) if False else None  # noqa: keep composite unique via raw SQL below
        op.drop_constraint("uq_fact_promotion_product_composite", "fact_promotion_product", type_="unique")
        op.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX uq_fact_promotion_product_composite
                ON fact_promotion_product (
                    promotion_id, product_id,
                    COALESCE(distributor_id, 0),
                    COALESCE(customer_id, 0)
                )
                """
            )
        )

    # ── ALTER dim_promotion: add new columns ───────────────────────────────────
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "start_week"):
        op.add_column("dim_promotion", sa.Column("start_week", sa.Integer(), nullable=True))
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "start_year"):
        op.add_column("dim_promotion", sa.Column("start_year", sa.Integer(), nullable=True))
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "end_week"):
        op.add_column("dim_promotion", sa.Column("end_week", sa.Integer(), nullable=True))
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "end_year"):
        op.add_column("dim_promotion", sa.Column("end_year", sa.Integer(), nullable=True))
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "promotion_type"):
        op.add_column("dim_promotion", sa.Column("promotion_type", sa.String(length=64), nullable=True))
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "status"):
        op.add_column(
            "dim_promotion", sa.Column("status", sa.String(length=32), server_default="draft", nullable=False)
        )
    insp = get_inspector(bind)
    if not has_column(insp, "dim_promotion", "notes_extended"):
        op.add_column("dim_promotion", sa.Column("notes_extended", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    # ── Revert dim_promotion columns ──────────────────────────────────────────
    for col in ("notes_extended", "status", "promotion_type", "end_year", "end_week", "start_year", "start_week"):
        insp = get_inspector(bind)
        if has_column(insp, "dim_promotion", col):
            op.drop_column("dim_promotion", col)

    # ── Drop fact_promotion_product ───────────────────────────────────────────
    insp = get_inspector(bind)
    if has_table(insp, "fact_promotion_product"):
        op.execute(sa.text("DROP INDEX IF EXISTS uq_fact_promotion_product_composite"))
        op.drop_table("fact_promotion_product")

    # ── Drop dim_retailer_listing ─────────────────────────────────────────────
    insp = get_inspector(bind)
    if has_table(insp, "dim_retailer_listing"):
        op.drop_table("dim_retailer_listing")

    # ── Drop fact_customer_sales ──────────────────────────────────────────────
    insp = get_inspector(bind)
    if has_table(insp, "fact_customer_sales"):
        op.drop_table("fact_customer_sales")

    # ── Drop customer_product_alias ───────────────────────────────────────────
    insp = get_inspector(bind)
    if has_table(insp, "customer_product_alias"):
        op.drop_table("customer_product_alias")

    # ── Drop dim_store ────────────────────────────────────────────────────────
    insp = get_inspector(bind)
    if has_table(insp, "dim_store"):
        op.drop_table("dim_store")
