"""Swap fact upsert unique constraint from source_key to fact_upsert_key.

Revision ID: 20260630_0061
Revises: 20260630_0060

Requires ``merge_shipped_fact_identity_twins.py --confirm`` after ``20260630_0062`` when
duplicate ``fact_upsert_key`` rows exist (invoice_line drift twins).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_0061"
down_revision: Union[str, Sequence[str], None] = "20260630_0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    dupes = op.get_bind().execute(
        sa.text(
            """
            SELECT fact_upsert_key, count(*) AS n
            FROM fact_inbound_shipment
            GROUP BY fact_upsert_key
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if dupes is not None:
        raise RuntimeError(
            "Duplicate fact_upsert_key rows remain — run "
            "apps/api/scripts/merge_shipped_fact_identity_twins.py --confirm before this migration"
        )

    op.drop_constraint("uq_fact_inbound_shipment_source_key", "fact_inbound_shipment", type_="unique")
    op.create_index(
        "ix_fact_inbound_shipment_source_key",
        "fact_inbound_shipment",
        ["source_key"],
        unique=False,
    )
    op.drop_index("ix_fact_inbound_shipment_fact_upsert_key", table_name="fact_inbound_shipment")
    op.create_unique_constraint(
        "uq_fact_inbound_shipment_fact_upsert_key",
        "fact_inbound_shipment",
        ["fact_upsert_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_fact_inbound_shipment_fact_upsert_key", "fact_inbound_shipment", type_="unique")
    op.create_index(
        "ix_fact_inbound_shipment_fact_upsert_key",
        "fact_inbound_shipment",
        ["fact_upsert_key"],
        unique=False,
    )
    op.drop_index("ix_fact_inbound_shipment_source_key", table_name="fact_inbound_shipment")
    op.create_unique_constraint(
        "uq_fact_inbound_shipment_source_key",
        "fact_inbound_shipment",
        ["source_key"],
    )
