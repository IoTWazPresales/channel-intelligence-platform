"""My accounts assignments: tenant, user, customer. No row-security policy.

Revision ID: 20261103_0052
Revises: 20261102_0051
Create Date: 2026-11-03

Warren, 3 Nov 2026. A row says which customer accounts a user starts on.
Empty means the My accounts filter starts off. The table does not create a
customer, a store, or a distributor, and it is not a permission. Do not apply
to cip until Warren says "run the migration".
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261103_0052"
down_revision: Union[str, Sequence[str], None] = "20261102_0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_customer_account (
            id bigserial PRIMARY KEY,
            tenant_id text NOT NULL REFERENCES tenant (id) ON DELETE CASCADE,
            user_id bigint NOT NULL REFERENCES app_user (id) ON DELETE CASCADE,
            customer_id integer NOT NULL REFERENCES dim_customer (id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_customer_account_tenant_user_customer
                UNIQUE (tenant_id, user_id, customer_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_user_customer_account_user_id ON user_customer_account (user_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_customer_account")
