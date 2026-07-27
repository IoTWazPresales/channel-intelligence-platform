"""Unit C — CPOR historical token surrogate (AUTHOR ONLY — do not apply to cip without Warren).

Revision ID: 20260727_0074
Revises: 20260720_0073

Adds ``import_cpor_historical_token_surrogate``: a stable numeric id per
(import_job_id, entity, token) pair for the historical CPOR steward workspace. Bookkeeping
only — never a dimension, never resolution truth. Replaces the client-side hash id
(``cporTokenRowId``) used for grid row keys / plan candidate ids with a real backend id.

Includes GRANT statements to role ``cip`` matching other CPOR tables (see
``docs/LOCAL_DEV_WINDOWS.md`` post-apply verification and 20260710_0072 /
20260702_0066 precedent) since table DML grants alone are not enough for
``INSERT … RETURNING id`` — the backing BIGSERIAL sequence also needs USAGE/SELECT.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0074"
down_revision: Union[str, Sequence[str], None] = "20260720_0073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "import_cpor_historical_token_surrogate"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "import_job_id",
            sa.Integer(),
            sa.ForeignKey("import_job.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("token", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "import_job_id", "entity", "token", name="uq_cpor_historical_token_surrogate_job_entity_token"
        ),
    )
    op.create_index(
        "ix_import_cpor_historical_token_surrogate_job",
        _TABLE,
        ["import_job_id"],
    )

    op.execute(sa.text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {_TABLE} TO cip"))
    op.execute(sa.text(f"GRANT USAGE, SELECT ON SEQUENCE {_TABLE}_id_seq TO cip"))


def downgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_job", table_name=_TABLE)
    op.drop_table(_TABLE)
