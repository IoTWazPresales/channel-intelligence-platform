"""Sell-out fact truth layer: source_key + staging_line lineage (DSI).

Revision ID: 20260517_0037
Revises: 20260515_0036

- Add ``source_key`` (global upsert identity, deterministic from grain).
- Add ``staging_line_id`` FK to ``import_distributor_si_staging_line`` (SET NULL on delete).
- Replace natural-key unique constraint with ``uq_fact_sales_sellout_source_key`` so latest DSI apply wins per key.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import fk_exists, get_inspector, has_column, unique_constraint_exists

revision: str = "20260517_0037"
down_revision: Union[str, Sequence[str], None] = "20260515_0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_column(insp, "fact_sales_sellout", "source_key"):
        op.add_column("fact_sales_sellout", sa.Column("source_key", sa.String(length=256), nullable=True))
    if not has_column(insp, "fact_sales_sellout", "staging_line_id"):
        op.add_column("fact_sales_sellout", sa.Column("staging_line_id", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE fact_sales_sellout
            SET source_key = 'dsi-sellout:'
                || COALESCE(distributor_id::text, '0') || ':'
                || customer_id::text || ':'
                || product_id::text || ':'
                || period_start::text
            WHERE source_key IS NULL
            """
        )
    )

    if unique_constraint_exists(insp, "fact_sales_sellout", "uq_fact_sales_sellout_dsi_v1"):
        op.drop_constraint("uq_fact_sales_sellout_dsi_v1", "fact_sales_sellout", type_="unique")
    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_sales_sellout", "uq_fact_sales_sellout_source_key"):
        op.create_unique_constraint(
            "uq_fact_sales_sellout_source_key",
            "fact_sales_sellout",
            ["source_key"],
        )

    op.alter_column("fact_sales_sellout", "source_key", existing_type=sa.String(length=256), nullable=False)

    if not fk_exists(insp, "fact_sales_sellout", "fk_fact_sales_sellout_staging_line_id"):
        op.create_foreign_key(
            "fk_fact_sales_sellout_staging_line_id",
            "fact_sales_sellout",
            "import_distributor_si_staging_line",
            ["staging_line_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if fk_exists(insp, "fact_sales_sellout", "fk_fact_sales_sellout_staging_line_id"):
        op.drop_constraint("fk_fact_sales_sellout_staging_line_id", "fact_sales_sellout", type_="foreignkey")

    if unique_constraint_exists(insp, "fact_sales_sellout", "uq_fact_sales_sellout_source_key"):
        op.drop_constraint("uq_fact_sales_sellout_source_key", "fact_sales_sellout", type_="unique")

    if not unique_constraint_exists(insp, "fact_sales_sellout", "uq_fact_sales_sellout_dsi_v1"):
        op.create_unique_constraint(
            "uq_fact_sales_sellout_dsi_v1",
            "fact_sales_sellout",
            ["distributor_id", "customer_id", "product_id", "period_start"],
        )

    if has_column(insp, "fact_sales_sellout", "staging_line_id"):
        op.drop_column("fact_sales_sellout", "staging_line_id")
    if has_column(insp, "fact_sales_sellout", "source_key"):
        op.drop_column("fact_sales_sellout", "source_key")
