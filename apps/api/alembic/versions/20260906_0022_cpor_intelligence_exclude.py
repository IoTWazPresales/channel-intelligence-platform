"""Visible reversible intelligence_exclude flag on cpor_case.

Revision ID: 20260906_0022
Revises: 20260905_0021
Create Date: 2026-09-06

Additive boolean, default false. Seeds the seven identified smoke/B4/operator-named
fixture cases. Does not delete rows. Reversible: downgrade drops the column;
operators can also clear the flag in product UI after this lands.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260906_0022"
down_revision: Union[str, Sequence[str], None] = "20260905_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Explicit codes only — do not ILIKE '%test%' (that would catch real MTN
# "Previous Sample Testing Support" C24233826>C24659732).
_SEED_CODES = (
    "C26C00001",
    "BATCH0-SMOKE-001",
    "H2-SMOKE-556",
    "C23C16018",
    "C26C00002",
    "C26C00003",
    "C26C00004",
)


def upgrade() -> None:
    op.add_column(
        "cpor_case",
        sa.Column(
            "intelligence_exclude",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_cpor_case_intelligence_exclude",
        "cpor_case",
        ["intelligence_exclude"],
    )
    quoted = ", ".join("'" + code.replace("'", "''") + "'" for code in _SEED_CODES)
    op.execute(
        sa.text(
            f"UPDATE cpor_case SET intelligence_exclude = TRUE WHERE case_code IN ({quoted})"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_cpor_case_intelligence_exclude", table_name="cpor_case")
    op.drop_column("cpor_case", "intelligence_exclude")
