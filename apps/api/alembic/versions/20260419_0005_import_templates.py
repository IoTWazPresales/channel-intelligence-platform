"""Import templates vs provider sources; import_job mode + template slug.

Revision ID: 20260419_0005
Revises: 20260418_0004
Create Date: 2026-04-19

``import_template`` / ``import_job`` / ``source_definition`` may already match the ORM
from 20260412_0001 ``create_all``. DDL here is guarded so a clean database upgrade does
not fail on duplicate tables or columns; seed SQL remains idempotent where possible.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import fk_exists, get_inspector, has_column, has_table
from app.services.imports.template_definitions import DEFAULT_SOURCES, IMPORT_TEMPLATE_ROWS

revision: str = "20260419_0005"
down_revision: Union[str, Sequence[str], None] = "20260418_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "import_template"):
        op.create_table(
            "import_template",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=256), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("admin_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("requires_provider", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("pipeline_handler", sa.String(length=64), nullable=False),
            sa.Column(
                "destructive_apply_requires_confirm",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("accepted_file_types", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("expected_columns", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )

    insp = get_inspector(bind)
    if not has_column(insp, "source_definition", "import_template_id"):
        op.add_column("source_definition", sa.Column("import_template_id", sa.Integer(), nullable=True))
    insp = get_inspector(bind)
    if not fk_exists(insp, "source_definition", "fk_source_definition_import_template"):
        op.create_foreign_key(
            "fk_source_definition_import_template",
            "source_definition",
            "import_template",
            ["import_template_id"],
            ["id"],
        )

    insp = get_inspector(bind)
    if not has_column(insp, "import_job", "import_mode"):
        op.add_column(
            "import_job",
            sa.Column("import_mode", sa.String(length=32), nullable=False, server_default="apply"),
        )
    insp = get_inspector(bind)
    if not has_column(insp, "import_job", "template_slug"):
        op.add_column("import_job", sa.Column("template_slug", sa.String(length=64), nullable=True))

    conn = op.get_bind()

    for t in IMPORT_TEMPLATE_ROWS:
        conn.execute(
            sa.text(
                """
                INSERT INTO import_template (
                    slug, display_name, description, enabled, hidden, admin_only,
                    requires_provider, pipeline_handler, destructive_apply_requires_confirm,
                    accepted_file_types, expected_columns
                ) VALUES (
                    :slug, :display_name, :description, :enabled, :hidden, :admin_only,
                    :requires_provider, :pipeline_handler, :destructive,
                    CAST(:accepted AS jsonb), CAST(:expected AS jsonb)
                )
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {
                "slug": t["slug"],
                "display_name": t["display_name"],
                "description": t["description"],
                "enabled": t["enabled"],
                "hidden": t["hidden"],
                "admin_only": t["admin_only"],
                "requires_provider": t["requires_provider"],
                "pipeline_handler": t["pipeline_handler"],
                "destructive": t["destructive_apply_requires_confirm"],
                "accepted": json.dumps(t["accepted_file_types"]),
                "expected": json.dumps(t["expected_columns"]),
            },
        )

    conn.execute(
        sa.text(
            """
            UPDATE source_definition sd
            SET import_template_id = it.id
            FROM import_template it
            WHERE it.slug = 'distributor_inventory'
              AND sd.code = 'distributor_inventory'
            """
        )
    )

    for code, name, tpl_slug, kind in DEFAULT_SOURCES:
        conn.execute(
            sa.text(
                """
                INSERT INTO source_definition (
                    import_template_id, code, name, source_kind, expected_template, parser_module, is_active
                )
                SELECT it.id,
                       CAST(:code AS varchar(64)),
                       CAST(:name AS varchar(256)),
                       CAST(:kind AS varchar(64)),
                       CAST(NULL AS jsonb),
                       CAST(NULL AS varchar(256)),
                       CASE WHEN it.hidden OR NOT it.enabled THEN false ELSE true END
                FROM import_template it
                WHERE it.slug = CAST(:tpl_slug AS varchar(64))
                  AND NOT EXISTS (SELECT 1 FROM source_definition s WHERE s.code = CAST(:code AS varchar(64)))
                """
            ),
            {"code": code, "name": name, "kind": kind, "tpl_slug": tpl_slug},
        )

    conn.execute(
        sa.text(
            """
            UPDATE source_definition
            SET import_template_id = (SELECT id FROM import_template WHERE slug = 'distributor_inventory' LIMIT 1)
            WHERE import_template_id IS NULL
            """
        )
    )

    insp = get_inspector(bind)
    it_id_col = next(
        (c for c in insp.get_columns("source_definition") if c.get("name") == "import_template_id"),
        None,
    )
    if it_id_col is not None and it_id_col.get("nullable", True):
        op.alter_column("source_definition", "import_template_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_column(insp, "import_job", "template_slug"):
        op.drop_column("import_job", "template_slug")
    insp = get_inspector(bind)
    if has_column(insp, "import_job", "import_mode"):
        op.drop_column("import_job", "import_mode")

    insp = get_inspector(bind)
    if fk_exists(insp, "source_definition", "fk_source_definition_import_template"):
        op.drop_constraint("fk_source_definition_import_template", "source_definition", type_="foreignkey")
    insp = get_inspector(bind)
    if has_column(insp, "source_definition", "import_template_id"):
        op.drop_column("source_definition", "import_template_id")

    insp = get_inspector(bind)
    if has_table(insp, "import_template"):
        op.drop_table("import_template")
