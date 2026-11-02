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


REPORT_TYPES_ALWAYS_OPEN = ("xxomrpt0027_order", "acza_workbook_unship", "acza_workbook_bom_not_ready")
REPORT_TYPES_ALWAYS_SHIPPED = ("xxomrpt0025_shipment",)

# Two retire paths write 'closed_superseded', from two different states:
#   * the PO-less twin retire: the row was 'shipped' (PO-less, delivery + item);
#   * the orphan open-row retire (20261102): the row was 'open_order' with no evidence line.
# The downgrade puts each row back to the state it had. The state is read from what the retire leaves untouched:
#   1. the report type, when it fixes the state (an order report is open, the XXOMRPT0025 shipment report is shipped);
#   2. otherwise (ACZA Shipped sheet, which holds both): the superseding fact is an open order -> the row was open;
#   3. otherwise: no ship confirm date -> open, a confirm date -> shipped.
# A row whose prior state cannot be told apart by 1-3 (an orphaned open Shipped-sheet line with a confirm date in the future
# whose replacement has since closed) comes back as 'shipped'. That is the one case the columns cannot settle.
_RESTORE_PRIOR_STATE_SQL = f"""
UPDATE fact_inbound_shipment f
SET line_state = CASE
  WHEN f.report_type IN ({", ".join(repr(t) for t in REPORT_TYPES_ALWAYS_OPEN)}) THEN 'open_order'
  WHEN f.report_type IN ({", ".join(repr(t) for t in REPORT_TYPES_ALWAYS_SHIPPED)}) THEN 'shipped'
  WHEN EXISTS (
    SELECT 1 FROM fact_inbound_shipment k
    WHERE k.tenant_id = f.tenant_id
      AND k.id <> f.id
      AND (k.fact_upsert_key = f.superseded_by_key OR k.id = f.superseded_by_fact_id)
      AND lower(k.line_state) = 'open_order'
  ) THEN 'open_order'
  WHEN f.ship_confirm_date IS NULL THEN 'open_order'
  ELSE 'shipped'
END
WHERE f.line_state = 'closed_superseded'
"""


def downgrade() -> None:
    # Put every retired row back to the state it had (see _RESTORE_PRIOR_STATE_SQL). Setting all of them to 'shipped'
    # turned the orphan-retired open orders into shipped units that never had a ship confirm date (GOV-008 M1).
    op.execute(_RESTORE_PRIOR_STATE_SQL)
    op.execute("ALTER TABLE fact_inbound_shipment DROP COLUMN IF EXISTS superseded_by_key")
    op.execute("ALTER TABLE fact_inbound_shipment DROP COLUMN IF EXISTS superseded_by_fact_id")
