"""Re-backfill shipped ``fact_upsert_key`` to PO-inclusive identity.

Revision ID: 20260630_0062
Revises: 20260630_0060

Shipped keys become ``ship:{OU|delivery|item|purchase_order_id}``. Run
``merge_shipped_fact_identity_twins.py --confirm`` after this (or rely on its
regenerate step) before ``20260630_0061``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_0062"
down_revision: Union[str, Sequence[str], None] = "20260630_0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_po_inclusive_keys(connection) -> None:
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
            key = stable_shipped_fact_upsert_key_from_fields(
                operating_unit=row["operating_unit"],
                delivery_no=row["delivery_no"],
                item_code=row["item_code"],
                purchase_order_id=row["purchase_order_id"],
            ) or str(row["source_key"])
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
                    "purchase_order_id": row["purchase_order_id"],
                }
            )
        connection.execute(
            sa.text("UPDATE fact_inbound_shipment SET fact_upsert_key = :k WHERE id = :id"),
            {"k": key[:256], "id": int(row["id"])},
        )


def upgrade() -> None:
    _backfill_po_inclusive_keys(op.get_bind())


def downgrade() -> None:
    from app.services.imports.shipment_evidence_line_identity import (
        fact_upsert_key_for_evidence_values,
        stable_shipped_fact_upsert_key_from_fields,
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, line_state, source_key, operating_unit, delivery_no, item_code,
                   order_no, order_line
            FROM fact_inbound_shipment
            """
        )
    ).mappings().all()
    for row in rows:
        if (row["line_state"] or "").strip().lower() == "shipped":
            key = stable_shipped_fact_upsert_key_from_fields(
                operating_unit=row["operating_unit"],
                delivery_no=row["delivery_no"],
                item_code=row["item_code"],
            ) or str(row["source_key"])
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
