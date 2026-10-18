"""Sell-through staging: one column per product identifier, and how the product was found.

Revision ID: 20261019_0044
Revises: 20261016_0043
Create Date: 2026-10-19

N-0111 (Warren 2026-10-19): the sell-through column-mapping step offers Part number, Barcode and
Sales model / marketing name as separate columns beside the customer's own product code. Staging keeps
each identifier apart, and records the Product Master field that matched (or that the identifiers
disagreed) for every row.

Additive: five nullable columns on ``import_customer_sellthrough_staging_line``; no existing row
changes. Needs the table owner (on cip: ``postgres``), so run it with DATABASE_URL_SYNC_MIGRATE set
to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261019_0044"
down_revision: Union[str, Sequence[str], None] = "20261016_0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "import_customer_sellthrough_staging_line"
COLUMNS = (
    ("raw_part_number_token", "varchar(256)"),
    ("raw_barcode_token", "varchar(256)"),
    ("raw_sales_model_token", "varchar(256)"),
    ("product_match_tier", "varchar(32)"),
    ("product_identifier_check", "jsonb"),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _kind in reversed(COLUMNS):
        op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {name}")
