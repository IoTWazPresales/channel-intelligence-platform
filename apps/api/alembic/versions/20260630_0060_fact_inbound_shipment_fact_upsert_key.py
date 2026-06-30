"""fact_inbound_shipment fact_upsert_key — invoice-line-agnostic shipped identity.

Revision ID: 20260630_0060
Revises: 20260629_0059

Adds ``fact_upsert_key`` and backfills:
  * shipped → ``ship:{OU|delivery|item}`` (stable across invoice_line drift)
  * other line states → existing ``source_key``

Run ``merge_shipped_fact_identity_twins.py`` (preview then --confirm) before upgrading to
``20260630_0061`` which swaps the unique constraint to ``fact_upsert_key``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_0060"
down_revision: Union[str, Sequence[str], None] = "20260629_0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_fact_upsert_keys(connection) -> None:
    from app.services.imports.shipment_evidence_line_identity import (
        fact_upsert_key_for_evidence_values,
        stable_shipped_fact_upsert_key_from_fields,
    )

    rows = connection.execute(
        sa.text(
            """
            SELECT id, line_state, source_key, operating_unit, delivery_no, item_code,
                   order_no, order_line, purchase_order_id
            FROM fact_inbound_shipment
            """
        )
    ).mappings().all()

    for row in rows:
        if (row["line_state"] or "").strip().lower() == "shipped":
            stable = stable_shipped_fact_upsert_key_from_fields(
                operating_unit=row["operating_unit"],
                delivery_no=row["delivery_no"],
                item_code=row["item_code"],
                purchase_order_id=row["purchase_order_id"],
            )
            key = stable or str(row["source_key"])
        else:
            key = fact_upsert_key_for_evidence_values(
                {
                    "line_state": row["line_state"],
                    "source_key": row["source_key"],
                    "operating_unit": row["operating_unit"],
                    "delivery_no": row["delivery_no"],
                    "item_code": row["item_code"],
                    "order_no": row["order_no"],
                    "order_line": row["order_line"],
                }
            )
        connection.execute(
            sa.text("UPDATE fact_inbound_shipment SET fact_upsert_key = :k WHERE id = :id"),
            {"k": key[:256], "id": int(row["id"])},
        )


def upgrade() -> None:
    op.add_column(
        "fact_inbound_shipment",
        sa.Column("fact_upsert_key", sa.String(length=256), nullable=True),
    )
    _backfill_fact_upsert_keys(op.get_bind())
    op.alter_column("fact_inbound_shipment", "fact_upsert_key", nullable=False)
    op.create_index(
        "ix_fact_inbound_shipment_fact_upsert_key",
        "fact_inbound_shipment",
        ["fact_upsert_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fact_inbound_shipment_fact_upsert_key", table_name="fact_inbound_shipment")
    op.drop_column("fact_inbound_shipment", "fact_upsert_key")
