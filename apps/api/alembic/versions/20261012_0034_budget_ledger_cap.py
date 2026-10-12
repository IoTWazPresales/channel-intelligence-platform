"""Allow an audited cap row on the budget ledger.

Revision ID: 20261012_0034
Revises: 20261012_0033
Create Date: 2026-10-12

A cap is a ceiling. It is not a pot and it is not summed into remaining.
The latest cap row for a product line and quarter is the current ceiling.
A null amount clears it. Update and delete stay refused.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0034"
down_revision: Union[str, Sequence[str], None] = "20261012_0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WITH_CAP = """
    entry_type IN (
        'reserve', 'transfer', 'commit', 'commit_adjust',
        'release', 'consume', 'paid', 'cap'
    )
"""

_WITHOUT_CAP = """
    entry_type IN (
        'reserve', 'transfer', 'commit', 'commit_adjust',
        'release', 'consume', 'paid'
    )
"""


def upgrade() -> None:
    op.execute("ALTER TABLE budget_ledger_entry DROP CONSTRAINT IF EXISTS ck_budget_ledger_entry_type")
    op.execute(
        f"ALTER TABLE budget_ledger_entry ADD CONSTRAINT ck_budget_ledger_entry_type CHECK ({_WITH_CAP})"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE budget_ledger_entry DISABLE TRIGGER budget_ledger_entry_append_only")
    op.execute("DELETE FROM budget_ledger_entry WHERE entry_type = 'cap'")
    op.execute("ALTER TABLE budget_ledger_entry DROP CONSTRAINT IF EXISTS ck_budget_ledger_entry_type")
    op.execute(
        f"ALTER TABLE budget_ledger_entry ADD CONSTRAINT ck_budget_ledger_entry_type CHECK ({_WITHOUT_CAP})"
    )
    op.execute("ALTER TABLE budget_ledger_entry ENABLE TRIGGER budget_ledger_entry_append_only")
