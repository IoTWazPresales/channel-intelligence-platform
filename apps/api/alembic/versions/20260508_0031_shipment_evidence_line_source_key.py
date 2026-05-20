"""Shipment evidence: stable source_key + unique (import_job_id, source_key).

Revision ID: 20260508_0031
Revises: 20260507_0030
Create Date: 2026-05-08

Adds ``source_key`` for id-stable re-import upserts. Existing rows are backfilled with
``legacy:{import_job_id}:{id}`` so uniqueness holds before NOT NULL is applied.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_0031"
down_revision: Union[str, Sequence[str], None] = "20260507_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shipment_evidence_line",
        sa.Column("source_key", sa.String(length=256), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE shipment_evidence_line SET source_key = "
            "'legacy:' || import_job_id::text || ':' || id::text "
            "WHERE source_key IS NULL"
        )
    )
    op.alter_column(
        "shipment_evidence_line",
        "source_key",
        existing_type=sa.String(length=256),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_shipment_evidence_line_import_job_source_key",
        "shipment_evidence_line",
        ["import_job_id", "source_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_shipment_evidence_line_import_job_source_key",
        "shipment_evidence_line",
        type_="unique",
    )
    op.drop_column("shipment_evidence_line", "source_key")
