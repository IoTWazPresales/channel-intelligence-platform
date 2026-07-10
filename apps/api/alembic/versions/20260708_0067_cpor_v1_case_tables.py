"""CPOR v1 tables: case, line, event, claim evidence (spec §3).

Revision ID: 20260708_0067
Revises: 20260702_0066

Does not alter commercial_customer_term (already has margin + rebate defaults).
Does not touch promo scaffold tables.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260708_0067"
down_revision: Union[str, Sequence[str], None] = "20260702_0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cpor_case",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_code", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("promotion_type", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("roe_snapshot", sa.Numeric(18, 6), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=False, server_default="ZAR"),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="reseller"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("export_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workflow_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("last_comment", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("superseded_by_case_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["superseded_by_case_id"],
            ["cpor_case.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_code", name="uq_cpor_case_case_code"),
    )
    op.create_index("ix_cpor_case_customer_id", "cpor_case", ["customer_id"])
    op.create_index("ix_cpor_case_superseded_by_case_id", "cpor_case", ["superseded_by_case_id"])
    op.create_index("ix_cpor_case_status", "cpor_case", ["status"])

    op.create_table(
        "cpor_case_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("pod_quarter", sa.String(length=16), nullable=True),
        sa.Column("srp", sa.Numeric(18, 4), nullable=False),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("dealer_margin_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column(
            "margin_source",
            sa.String(length=32),
            nullable=False,
            server_default="customer_default",
        ),
        sa.Column("cost_basis", sa.Numeric(18, 4), nullable=True),
        sa.Column("cost_source", sa.String(length=32), nullable=True),
        sa.Column("cost_evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("estimate_qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("cap_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("soh_snapshot", sa.Numeric(18, 4), nullable=True),
        sa.Column("dealer_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("support_unit", sa.Numeric(18, 4), nullable=True),
        sa.Column("ttl_support", sa.Numeric(18, 4), nullable=True),
        sa.Column("support_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("result_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("ttl_result", sa.Numeric(18, 4), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["case_id"], ["cpor_case.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id",
            "product_id",
            "distributor_id",
            "pod_quarter",
            name="uq_cpor_case_line_grain",
        ),
    )
    op.create_index("ix_cpor_case_line_case_id", "cpor_case_line", ["case_id"])
    op.create_index("ix_cpor_case_line_product_id", "cpor_case_line", ["product_id"])
    op.create_index("ix_cpor_case_line_distributor_id", "cpor_case_line", ["distributor_id"])

    op.create_table(
        "cpor_case_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cpor_case.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cpor_case_event_case_id", "cpor_case_event", ["case_id"])

    op.create_table(
        "cpor_claim_evidence_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("import_job_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("source_model_token", sa.String(length=256), nullable=True),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("units", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("raw_source_row", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_key", sa.String(length=256), nullable=False),
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
        sa.ForeignKeyConstraint(["case_id"], ["cpor_case.id"]),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_cpor_claim_evidence_line_source_key"),
    )
    op.create_index("ix_cpor_claim_evidence_line_case_id", "cpor_claim_evidence_line", ["case_id"])
    op.create_index(
        "ix_cpor_claim_evidence_line_import_job_id",
        "cpor_claim_evidence_line",
        ["import_job_id"],
    )
    op.create_index(
        "ix_cpor_claim_evidence_line_product_id",
        "cpor_claim_evidence_line",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_cpor_claim_evidence_line_product_id", table_name="cpor_claim_evidence_line")
    op.drop_index("ix_cpor_claim_evidence_line_import_job_id", table_name="cpor_claim_evidence_line")
    op.drop_index("ix_cpor_claim_evidence_line_case_id", table_name="cpor_claim_evidence_line")
    op.drop_table("cpor_claim_evidence_line")

    op.drop_index("ix_cpor_case_event_case_id", table_name="cpor_case_event")
    op.drop_table("cpor_case_event")

    op.drop_index("ix_cpor_case_line_distributor_id", table_name="cpor_case_line")
    op.drop_index("ix_cpor_case_line_product_id", table_name="cpor_case_line")
    op.drop_index("ix_cpor_case_line_case_id", table_name="cpor_case_line")
    op.drop_table("cpor_case_line")

    op.drop_index("ix_cpor_case_status", table_name="cpor_case")
    op.drop_index("ix_cpor_case_superseded_by_case_id", table_name="cpor_case")
    op.drop_index("ix_cpor_case_customer_id", table_name="cpor_case")
    op.drop_table("cpor_case")
