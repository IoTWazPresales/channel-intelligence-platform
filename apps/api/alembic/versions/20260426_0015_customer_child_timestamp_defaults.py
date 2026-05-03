"""Add timestamp defaults for customer child scaffold tables.

Revision ID: 20260426_0015
Revises: 20260426_0014
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260426_0015"
down_revision: Union[str, Sequence[str], None] = "20260426_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("customer_location", "created_at", server_default=sa.text("now()"))
    op.alter_column("customer_location", "updated_at", server_default=sa.text("now()"))
    op.alter_column("customer_contact", "created_at", server_default=sa.text("now()"))
    op.alter_column("customer_contact", "updated_at", server_default=sa.text("now()"))


def downgrade() -> None:
    op.alter_column("customer_contact", "updated_at", server_default=None)
    op.alter_column("customer_contact", "created_at", server_default=None)
    op.alter_column("customer_location", "updated_at", server_default=None)
    op.alter_column("customer_location", "created_at", server_default=None)
