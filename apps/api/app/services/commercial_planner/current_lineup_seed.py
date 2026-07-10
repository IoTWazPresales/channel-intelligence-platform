"""Idempotent seed for lineup ImportTemplate + SourceDefinition rows.

Generic over (template_slug, source_code) so it serves both the legacy ``current_lineup``
(Commercial-Planner embedded upload) and the first-class ``unified_lineup`` (Import-Centre
multi-file) importers.

Used by:
- Alembic migrations (sync, via ``op.get_bind()``)
- Runtime parse paths (async, self-heal if a migration has not been applied yet)

Must stay aligned with apps/api/app/services/imports/template_definitions.py (template rows +
DEFAULT_SOURCES).
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.imports.template_definitions import DEFAULT_SOURCES, IMPORT_TEMPLATE_ROWS


class CurrentLineupSourceNotConfiguredError(Exception):
    """Raised when a lineup template or its system source cannot be resolved."""

    def __init__(self, message: str, *, remediation: str) -> None:
        super().__init__(message)
        self.remediation = remediation


# Backwards-compatible alias: the generic name reads better at unified-lineup call sites.
LineupSourceNotConfiguredError = CurrentLineupSourceNotConfiguredError


_TEMPLATE_UPSERT_SQL = """
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

_SOURCE_INSERT_SQL = """
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


def _template_row(template_slug: str) -> dict:
    return next(t for t in IMPORT_TEMPLATE_ROWS if t["slug"] == template_slug)


def _template_params(template_slug: str) -> dict:
    t = _template_row(template_slug)
    return {
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
    }


def _source_params(template_slug: str, source_code: str) -> dict | None:
    for code, name, tpl_slug, kind in DEFAULT_SOURCES:
        if tpl_slug == template_slug and code == source_code:
            return {"code": code, "name": name, "kind": kind, "tpl_slug": tpl_slug}
    return None


async def ensure_lineup_import_seed(
    db: AsyncSession, *, template_slug: str, source_code: str
) -> None:
    """Async idempotent upsert of a lineup template + its system source (safe every call)."""
    await db.execute(text(_TEMPLATE_UPSERT_SQL), _template_params(template_slug))
    src = _source_params(template_slug, source_code)
    if src is not None:
        await db.execute(text(_SOURCE_INSERT_SQL), src)
    await db.flush()


def ensure_lineup_import_seed_sync(conn, *, template_slug: str, source_code: str) -> None:
    """Sync idempotent seed for Alembic migrations (op.get_bind())."""
    conn.execute(text(_TEMPLATE_UPSERT_SQL), _template_params(template_slug))
    src = _source_params(template_slug, source_code)
    if src is not None:
        conn.execute(text(_SOURCE_INSERT_SQL), src)


# ── Backwards-compatible current_lineup wrappers ────────────────────────────────


async def ensure_current_lineup_import_seed(db: AsyncSession) -> None:
    await ensure_lineup_import_seed(
        db, template_slug="current_lineup", source_code="current_lineup_system"
    )


def ensure_current_lineup_import_seed_sync(conn) -> None:
    ensure_lineup_import_seed_sync(
        conn, template_slug="current_lineup", source_code="current_lineup_system"
    )
