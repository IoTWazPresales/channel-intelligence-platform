"""fact_inbound_shipment: the shipped-identity key is unique per tenant, not globally.

Revision ID: 20261102_0051
Revises: 20261101_0050
Create Date: 2026-11-02

GOV-008 review 2 Nov, M5(b). ``fact_upsert_key`` is built from operating unit, delivery, item and PO and carries no tenant,
and ``uq_fact_inbound_shipment_fact_upsert_key`` was UNIQUE (fact_upsert_key). The shipped load replaces facts by that key,
so tenant B loading a line with the same identity as tenant A deleted tenant A's fact (probe P8).

The constraint keeps its name (the open-order upsert names it in ``ON CONFLICT ON CONSTRAINT``) and becomes
UNIQUE (tenant_id, fact_upsert_key). Nothing is rewritten: key strings are unchanged, so every existing fact still matches
its key. A table that already satisfies the global constraint satisfies the wider one, so the upgrade cannot fail on data.

The downgrade restores the global constraint and refuses when two tenants hold the same key.

NOT APPLIED to ``cip`` by the batch-2 session. Apply with the code that scopes the shipped replace by tenant (the code is
safe on the old constraint too: a cross-tenant key then fails loudly instead of deleting the other tenant's fact).
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261102_0051"
down_revision: Union[str, Sequence[str], None] = "20261101_0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNIQUE_NAME = "uq_fact_inbound_shipment_fact_upsert_key"


def upgrade() -> None:
    op.execute(f"ALTER TABLE fact_inbound_shipment DROP CONSTRAINT IF EXISTS {UNIQUE_NAME}")
    op.execute(f"ALTER TABLE fact_inbound_shipment ADD CONSTRAINT {UNIQUE_NAME} UNIQUE (tenant_id, fact_upsert_key)")


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM fact_inbound_shipment WHERE fact_upsert_key IS NOT NULL
            GROUP BY fact_upsert_key HAVING count(*) > 1 LIMIT 1
          ) THEN
            RAISE EXCEPTION 'Two tenants hold the same fact_upsert_key: the global unique constraint cannot be restored';
          END IF;
        END $$;
        """
    )
    op.execute(f"ALTER TABLE fact_inbound_shipment DROP CONSTRAINT IF EXISTS {UNIQUE_NAME}")
    op.execute(f"ALTER TABLE fact_inbound_shipment ADD CONSTRAINT {UNIQUE_NAME} UNIQUE (fact_upsert_key)")
