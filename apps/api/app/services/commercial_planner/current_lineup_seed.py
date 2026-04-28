"""Idempotent seed for current_lineup ImportTemplate + current_lineup_system SourceDefinition.

Used by:
- Alembic migration 20260428_0021 (mirrors this logic for offline `alembic upgrade head`)
- Runtime: parse_current_lineup_file (self-heal if migration not applied yet)

Must stay aligned with apps/api/app/services/imports/template_definitions.py for slug current_lineup
and DEFAULT_SOURCES entry current_lineup_system.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.imports.template_definitions import DEFAULT_SOURCES, IMPORT_TEMPLATE_ROWS


class CurrentLineupSourceNotConfiguredError(Exception):
    """Raised when current_lineup template or current_lineup_system source cannot be resolved."""

    def __init__(self, message: str, *, remediation: str) -> None:
        super().__init__(message)
        self.remediation = remediation


def _current_lineup_template_row() -> dict:
    row = next(t for t in IMPORT_TEMPLATE_ROWS if t["slug"] == "current_lineup")
    return row


async def ensure_current_lineup_import_seed(db: AsyncSession) -> None:
    """Upsert current_lineup template and insert current_lineup_system source if missing.

    Idempotent and safe to call on every parse-upload.
    (SQL duplicated in ensure_current_lineup_import_seed_sync for Alembic — keep both in sync.)
    """
    t = _current_lineup_template_row()
    await db.execute(
        text(
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
        if tpl_slug != "current_lineup" or code != "current_lineup_system":
            continue
        await db.execute(
            text(
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

    await db.flush()


def ensure_current_lineup_import_seed_sync(conn) -> None:
    """Synchronous idempotent seed for Alembic migrations (op.get_bind())."""
    t = _current_lineup_template_row()
    conn.execute(
        text(
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
        if tpl_slug != "current_lineup" or code != "current_lineup_system":
            continue
        conn.execute(
            text(
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
