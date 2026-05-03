"""Distributor source token alias + audit columns on customer_source_token_alias.

Revision ID: 20260430_0027
Revises: 20260430_0026
Create Date: 2026-04-30

``distributor_source_token_alias`` and audit FK columns on ``customer_source_token_alias``
may already exist from 20260412_0001 ``create_all``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import fk_exists, get_inspector, has_column, has_index, has_table

revision: str = "20260430_0027"
down_revision: Union[str, Sequence[str], None] = "20260430_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "distributor_source_token_alias"):
        op.create_table(
            "distributor_source_token_alias",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("distributor_id", sa.Integer(), nullable=False),
            sa.Column("source_definition_id", sa.Integer(), nullable=True),
            sa.Column("raw_token", sa.String(length=512), nullable=False),
            sa.Column("normalized_token", sa.String(length=512), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="approved"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_from_import_job_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_definition_id"], ["source_definition.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_from_import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "distributor_source_token_alias", "ix_distributor_source_token_alias_norm"):
        op.create_index(
            "ix_distributor_source_token_alias_norm",
            "distributor_source_token_alias",
            ["normalized_token"],
        )

    insp = get_inspector(bind)
    if not has_column(insp, "customer_source_token_alias", "created_from_import_job_id"):
        op.add_column(
            "customer_source_token_alias",
            sa.Column("created_from_import_job_id", sa.Integer(), nullable=True),
        )
    insp = get_inspector(bind)
    if not has_column(insp, "customer_source_token_alias", "import_entity_mapping_candidate_id"):
        op.add_column(
            "customer_source_token_alias",
            sa.Column("import_entity_mapping_candidate_id", sa.Integer(), nullable=True),
        )
    insp = get_inspector(bind)
    if not fk_exists(insp, "customer_source_token_alias", "fk_csta_created_from_import_job"):
        op.create_foreign_key(
            "fk_csta_created_from_import_job",
            "customer_source_token_alias",
            "import_job",
            ["created_from_import_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
    insp = get_inspector(bind)
    if not fk_exists(insp, "customer_source_token_alias", "fk_csta_import_entity_mapping_candidate"):
        op.create_foreign_key(
            "fk_csta_import_entity_mapping_candidate",
            "customer_source_token_alias",
            "import_entity_mapping_candidate",
            ["import_entity_mapping_candidate_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if fk_exists(insp, "customer_source_token_alias", "fk_csta_import_entity_mapping_candidate"):
        op.drop_constraint("fk_csta_import_entity_mapping_candidate", "customer_source_token_alias", type_="foreignkey")
    insp = get_inspector(bind)
    if fk_exists(insp, "customer_source_token_alias", "fk_csta_created_from_import_job"):
        op.drop_constraint("fk_csta_created_from_import_job", "customer_source_token_alias", type_="foreignkey")
    insp = get_inspector(bind)
    if has_column(insp, "customer_source_token_alias", "import_entity_mapping_candidate_id"):
        op.drop_column("customer_source_token_alias", "import_entity_mapping_candidate_id")
    insp = get_inspector(bind)
    if has_column(insp, "customer_source_token_alias", "created_from_import_job_id"):
        op.drop_column("customer_source_token_alias", "created_from_import_job_id")

    insp = get_inspector(bind)
    if has_index(insp, "distributor_source_token_alias", "ix_distributor_source_token_alias_norm"):
        op.drop_index("ix_distributor_source_token_alias_norm", table_name="distributor_source_token_alias")
    insp = get_inspector(bind)
    if has_table(insp, "distributor_source_token_alias"):
        op.drop_table("distributor_source_token_alias")
