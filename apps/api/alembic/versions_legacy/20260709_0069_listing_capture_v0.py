"""LC-U1 — customer_listing + listing_observation (AUTHOR ONLY — do not apply to cip without Warren).

Revision ID: 20260709_0069
Revises: 20260709_0068
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260709_0069"
down_revision: Union[str, Sequence[str], None] = "20260709_0068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_listing",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("dim_customer.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("dim_product.id"), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("registered_by", sa.String(length=128), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "url", name="uq_customer_listing_customer_url"),
    )
    op.create_index("ix_customer_listing_customer_id", "customer_listing", ["customer_id"])
    op.create_index("ix_customer_listing_product_id", "customer_listing", ["product_id"])
    op.create_index("ix_customer_listing_marketplace", "customer_listing", ["marketplace"])

    op.create_table(
        "listing_observation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("customer_listing.id"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("raw_snapshot", sa.LargeBinary(), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("extracted_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("extracted_availability", sa.String(length=64), nullable=True),
        sa.Column("extracted_promo_badge", sa.String(length=128), nullable=True),
        sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("parse_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_observation_listing_id", "listing_observation", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_listing_observation_listing_id", table_name="listing_observation")
    op.drop_table("listing_observation")
    op.drop_index("ix_customer_listing_marketplace", table_name="customer_listing")
    op.drop_index("ix_customer_listing_product_id", table_name="customer_listing")
    op.drop_index("ix_customer_listing_customer_id", table_name="customer_listing")
    op.drop_table("customer_listing")
