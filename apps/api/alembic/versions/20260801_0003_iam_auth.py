"""IAM auth tables + seed default tenant and admin (P2-3).

Revision ID: 20260801_0003
Revises: 20260801_0002
Create Date: 2026-08-01

Seed admin (change after first login):
  email: admin@local
  password: changeme

Idempotent: tip-ORM ``20260801_0001`` create_all may already have the tables;
seed + grants still run.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260801_0003"
down_revision: Union[str, Sequence[str], None] = "20260801_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# pbkdf2_sha256$260000$… for password "changeme" (stdlib hasher in app.core.password)
_ADMIN_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$63c4ad2dd697f8a22c2020477d787112$"
    "7f705f78fbae422fda7f62b6ea052d556a1f63ffaa86593077e1132e72ebe4c5"
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "tenant" not in tables:
        op.create_table(
            "tenant",
            sa.Column("id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="pk_tenant"),
        )

    if "app_user" not in tables:
        op.create_table(
            "app_user",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id"],
                ["tenant.id"],
                name="fk_app_user_tenant_id_tenant",
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_app_user"),
            sa.UniqueConstraint("tenant_id", "email", name="uq_app_user_tenant_email"),
        )
        op.create_index("ix_app_user_tenant_id", "app_user", ["tenant_id"])

    if "auth_session" not in tables:
        op.create_table(
            "auth_session",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["app_user.id"],
                name="fk_auth_session_user_id_app_user",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_auth_session"),
            sa.UniqueConstraint("token_hash", name="uq_auth_session_token_hash"),
        )
        op.create_index("ix_auth_session_user_id", "auth_session", ["user_id"])

    op.execute(
        sa.text(
            "INSERT INTO tenant (id, name) VALUES ('default', 'Default tenant') "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO app_user (tenant_id, email, password_hash, display_name, role, is_active)
            SELECT 'default', 'admin@local', :ph, 'Local Admin', 'admin', true
            WHERE NOT EXISTS (
              SELECT 1 FROM app_user
              WHERE tenant_id = 'default' AND email = 'admin@local'
            )
            """
        ).bindparams(ph=_ADMIN_PASSWORD_HASH)
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON tenant TO cip';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON app_user TO cip';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON auth_session TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE app_user_id_seq TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE auth_session_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "auth_session" in tables:
        op.drop_table("auth_session")
    if "app_user" in tables:
        op.drop_table("app_user")
    if "tenant" in tables:
        op.drop_table("tenant")
