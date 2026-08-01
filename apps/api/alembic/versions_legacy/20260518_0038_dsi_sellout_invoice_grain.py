"""DSI sell-out day grain: staging invoice_no, fact transaction_date + invoice_no.

Revision ID: 20260518_0038
Revises: 20260517_0037

- ``import_distributor_si_staging_line.invoice_no`` nullable; missing values stored as ``''``
  (empty string sentinel — deterministic in source_key hash, not NULL).
- ``fact_sales_sellout.transaction_date`` and ``invoice_no`` (NOT NULL default ``''``).
- Both ``period_start`` and ``transaction_date`` populated from the same staging transaction date
  on apply (sell-out API still reads ``period_start``).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_column

revision: str = "20260518_0038"
down_revision: Union[str, Sequence[str], None] = "20260517_0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_column(insp, "import_distributor_si_staging_line", "invoice_no"):
        op.add_column(
            "import_distributor_si_staging_line",
            sa.Column("invoice_no", sa.String(length=128), nullable=True),
        )
    op.execute(
        sa.text(
            """
            UPDATE import_distributor_si_staging_line
            SET invoice_no = ''
            WHERE invoice_no IS NULL
            """
        )
    )

    if not has_column(insp, "fact_sales_sellout", "transaction_date"):
        op.add_column("fact_sales_sellout", sa.Column("transaction_date", sa.Date(), nullable=True))
    if not has_column(insp, "fact_sales_sellout", "invoice_no"):
        op.add_column(
            "fact_sales_sellout",
            sa.Column("invoice_no", sa.String(length=128), nullable=True),
        )

    op.execute(
        sa.text(
            """
            UPDATE fact_sales_sellout
            SET transaction_date = period_start
            WHERE transaction_date IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE fact_sales_sellout
            SET invoice_no = ''
            WHERE invoice_no IS NULL
            """
        )
    )

    op.alter_column("fact_sales_sellout", "transaction_date", existing_type=sa.Date(), nullable=False)
    op.alter_column(
        "fact_sales_sellout",
        "invoice_no",
        existing_type=sa.String(length=128),
        nullable=False,
        server_default="",
    )
    op.alter_column("fact_sales_sellout", "invoice_no", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_column(insp, "fact_sales_sellout", "invoice_no"):
        op.drop_column("fact_sales_sellout", "invoice_no")
    if has_column(insp, "fact_sales_sellout", "transaction_date"):
        op.drop_column("fact_sales_sellout", "transaction_date")
    if has_column(insp, "import_distributor_si_staging_line", "invoice_no"):
        op.drop_column("import_distributor_si_staging_line", "invoice_no")
