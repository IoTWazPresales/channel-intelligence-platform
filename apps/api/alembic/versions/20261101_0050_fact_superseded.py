"""fact_inbound_shipment: superseded pointer for shipped facts that lost their PO-less identity.

Revision ID: 20261101_0050
Revises: 20261101_0049
Create Date: 2026-11-01

A shipped fact with no purchase_order_id keeps its old ``fact_upsert_key``. When a newer job writes the same delivery and
item under the PO-inclusive key, the old row is never touched again and keeps counting. The retire step
(``scripts/merge_shipped_fact_identity_twins.py --retire-po-less``) sets ``line_state = 'closed_superseded'`` and fills
these two nullable columns; nothing is deleted. Both are plain columns (no foreign key): the shipped upsert replaces a
fact row on every reload, so the key is the stable pointer and the id is refreshed from it.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261101_0050"
down_revision: Union[str, Sequence[str], None] = "20261101_0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE fact_inbound_shipment ADD COLUMN IF NOT EXISTS superseded_by_fact_id integer")
    op.execute("ALTER TABLE fact_inbound_shipment ADD COLUMN IF NOT EXISTS superseded_by_key varchar(256)")


def downgrade() -> None:
    # A retired row was 'shipped' (and PO-less) before: put it back, so the downgrade leaves the table as it was.
    op.execute("UPDATE fact_inbound_shipment SET line_state = 'shipped' WHERE line_state = 'closed_superseded'")
    op.execute("ALTER TABLE fact_inbound_shipment DROP COLUMN IF EXISTS superseded_by_key")
    op.execute("ALTER TABLE fact_inbound_shipment DROP COLUMN IF EXISTS superseded_by_fact_id")
