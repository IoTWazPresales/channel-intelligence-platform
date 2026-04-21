"""Product catalogs, business units, catalog products, EAV attributes, source→catalog link.

Revision ID: 20260421_0007
Revises: 20260420_0006
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260421_0007"
down_revision: Union[str, Sequence[str], None] = "20260420_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_unit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_business_unit"),
        sa.UniqueConstraint("code", name="uq_business_unit_code"),
    )

    op.create_table(
        "product_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("business_unit_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["business_unit_id"],
            ["business_unit.id"],
            name="fk_pc_business_unit_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_catalog"),
        sa.UniqueConstraint("business_unit_id", "code", name="uq_product_catalog_bu_code"),
    )

    op.create_table(
        "attribute_definition",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("namespace", sa.String(length=256), nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=True),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["product_catalog.id"],
            name="fk_attr_def_catalog_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attribute_definition"),
        sa.UniqueConstraint("namespace", name="uq_attribute_definition_namespace"),
    )

    op.create_table(
        "catalog_product",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column("source_sku", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("canonical_product_id", sa.Integer(), nullable=True),
        sa.Column("source_metadata_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_import_job_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["product_catalog.id"],
            name="fk_cat_prod_catalog_id",
        ),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"],
            ["dim_product.id"],
            name="fk_cat_prod_canonical_id",
        ),
        sa.ForeignKeyConstraint(
            ["last_import_job_id"],
            ["import_job.id"],
            name="fk_cat_prod_import_job_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_product"),
        sa.UniqueConstraint("catalog_id", "source_sku", name="uq_catalog_product_catalog_sku"),
    )

    op.create_table(
        "product_attribute_value",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_product_id", sa.Integer(), nullable=False),
        sa.Column("attribute_definition_id", sa.Integer(), nullable=False),
        sa.Column("value_json", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["attribute_definition_id"],
            ["attribute_definition.id"],
            name="fk_pav_attr_def_id",
        ),
        sa.ForeignKeyConstraint(
            ["catalog_product_id"],
            ["catalog_product.id"],
            name="fk_pav_catalog_product_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_attribute_value"),
        sa.UniqueConstraint(
            "catalog_product_id",
            "attribute_definition_id",
            name="uq_pav_catalog_product_attr",
        ),
    )

    op.add_column(
        "source_definition",
        sa.Column("product_catalog_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sd_product_catalog_id",
        "source_definition",
        "product_catalog",
        ["product_catalog_id"],
        ["id"],
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO business_unit (code, name)
            SELECT 'platform', 'Platform'
            WHERE NOT EXISTS (SELECT 1 FROM business_unit WHERE code = 'platform')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO product_catalog (business_unit_id, code, name, is_active)
            SELECT bu.id, 'default_master', 'Default product master catalog', true
            FROM business_unit bu
            WHERE bu.code = 'platform'
              AND NOT EXISTS (
                  SELECT 1 FROM product_catalog pc WHERE pc.code = 'default_master' AND pc.business_unit_id = bu.id
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_sd_product_catalog_id",
        "source_definition",
        type_="foreignkey",
    )
    op.drop_column("source_definition", "product_catalog_id")

    op.drop_table("product_attribute_value")
    op.drop_table("catalog_product")
    op.drop_table("attribute_definition")
    op.drop_table("product_catalog")
    op.drop_table("business_unit")
