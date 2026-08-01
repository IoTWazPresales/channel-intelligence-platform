"""Seed distributor master import template and default source.

Revision ID: 20260426_0016
Revises: 20260426_0015
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import json
import sqlalchemy as sa
from alembic import op

revision: str = "20260426_0016"
down_revision: Union[str, Sequence[str], None] = "20260426_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO import_template (
                slug, display_name, description, enabled, hidden, admin_only,
                requires_provider, pipeline_handler, destructive_apply_requires_confirm,
                accepted_file_types, expected_columns
            ) VALUES (
                'distributor_master',
                'Distributor master',
                'Distributor master import with validation + apply upsert into dim_distributor.',
                true,
                false,
                false,
                true,
                'distributor_master_upsert',
                false,
                CAST(:accepted AS jsonb),
                CAST(:expected AS jsonb)
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
            "accepted": json.dumps([".csv", ".xlsx"]),
            "expected": json.dumps(
                {
                    "distributor_code": {
                        "aliases": ["code", "distributor_id", "account_code"],
                        "required": True,
                    },
                    "distributor_name": {
                        "aliases": ["name", "account_name", "canonical_name"],
                        "required": True,
                    },
                }
            ),
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO source_definition (
                import_template_id, code, name, source_kind, expected_template, parser_module, is_active
            )
            SELECT it.id,
                   CAST('distributor_master_default' AS varchar(64)),
                   CAST('Default distributor master feed' AS varchar(256)),
                   CAST('master_extract' AS varchar(64)),
                   CAST(NULL AS jsonb),
                   CAST(NULL AS varchar(256)),
                   true
            FROM import_template it
            WHERE it.slug = 'distributor_master'
              AND NOT EXISTS (SELECT 1 FROM source_definition s WHERE s.code = 'distributor_master_default')
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM source_definition WHERE code = 'distributor_master_default'"))
    conn.execute(sa.text("DELETE FROM import_template WHERE slug = 'distributor_master'"))
