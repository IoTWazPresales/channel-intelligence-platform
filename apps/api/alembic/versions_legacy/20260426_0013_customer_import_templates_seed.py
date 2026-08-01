"""Seed customer phase1 import templates and default sources.

Revision ID: 20260426_0013
Revises: 20260426_0012
Create Date: 2026-04-26
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.imports.template_definitions import DEFAULT_SOURCES, IMPORT_TEMPLATE_ROWS

revision: str = "20260426_0013"
down_revision: Union[str, Sequence[str], None] = "20260426_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
                ON CONFLICT (slug) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    enabled = EXCLUDED.enabled,
                    hidden = EXCLUDED.hidden,
                    admin_only = EXCLUDED.admin_only,
                    requires_provider = EXCLUDED.requires_provider,
                    pipeline_handler = EXCLUDED.pipeline_handler,
                    destructive_apply_requires_confirm = EXCLUDED.destructive_apply_requires_confirm,
                    accepted_file_types = EXCLUDED.accepted_file_types,
                    expected_columns = EXCLUDED.expected_columns
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


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM source_definition
            WHERE code IN (
                'customer_master_default',
                'customer_channel_mapping_default'
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM import_template
            WHERE slug IN ('customer_master', 'customer_channel_mapping')
            """
        )
    )
