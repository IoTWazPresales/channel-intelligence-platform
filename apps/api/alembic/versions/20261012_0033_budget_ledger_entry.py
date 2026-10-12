"""Append-only budget ledger.

Revision ID: 20261012_0033
Revises: 20261011_0032
Create Date: 2026-10-12

Balances are sums. Corrections are new rows. The app role may insert and
read. It may not update or delete.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0033"
down_revision: Union[str, Sequence[str], None] = "20261011_0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_ledger_entry (
            id bigserial PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            tenant_id text NOT NULL DEFAULT 'default',
            entry_type text NOT NULL,
            product_line text NOT NULL DEFAULT '',
            customer_id bigint,
            product_id bigint,
            landed_quarter text NOT NULL DEFAULT '',
            amount_usd numeric(18, 4),
            amount_local numeric(18, 4),
            fx_rate numeric(18, 8),
            case_id bigint,
            case_line_id bigint,
            lineup_item_id bigint,
            payment_evidence_id bigint,
            source_event_id text,
            actor text,
            reverses_entry_id bigint,
            source_tag text,
            CONSTRAINT ck_budget_ledger_entry_type CHECK (
                entry_type IN (
                    'reserve', 'transfer', 'commit', 'commit_adjust',
                    'release', 'consume', 'paid'
                )
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_budget_ledger_entry_line_quarter
            ON budget_ledger_entry (product_line, landed_quarter)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_budget_ledger_entry_case
            ON budget_ledger_entry (case_id)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_ledger_entry_no_mutate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'budget_ledger_entry is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS budget_ledger_entry_append_only ON budget_ledger_entry
        """
    )
    op.execute(
        """
        CREATE TRIGGER budget_ledger_entry_append_only
        BEFORE UPDATE OR DELETE ON budget_ledger_entry
        FOR EACH ROW EXECUTE FUNCTION budget_ledger_entry_no_mutate()
        """
    )
    op.execute("GRANT SELECT, INSERT ON budget_ledger_entry TO cip")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE budget_ledger_entry_id_seq TO cip")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS budget_ledger_entry_append_only ON budget_ledger_entry")
    op.execute("DROP FUNCTION IF EXISTS budget_ledger_entry_no_mutate()")
    op.execute("DROP TABLE IF EXISTS budget_ledger_entry")
