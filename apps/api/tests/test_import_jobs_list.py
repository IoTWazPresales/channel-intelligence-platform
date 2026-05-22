"""GET /imports/jobs list performance contract (lightweight columns + pagination)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.api.v1.endpoints.imports import list_jobs


def test_list_jobs_returns_paginated_items_without_jsonb_blobs() -> None:
    async def _run() -> None:
        row = MagicMock()
        row.id = 7
        row.source_id = 1
        row.template_slug = "distributor_inventory"
        row.import_mode = "validate"
        row.status = "completed"
        row.stage = "validated"
        row.file_name = "a.csv"
        row.error_summary = None
        row.archived_at = None
        row.created_at = None

        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        list_result = MagicMock()
        list_result.all.return_value = [row]

        db.execute = AsyncMock(side_effect=[count_result, list_result])

        out = await list_jobs(db=db, include_archived=False, limit=50, offset=0)

        assert out["total"] == 1
        assert out["limit"] == 50
        assert len(out["items"]) == 1
        item = out["items"][0]
        assert item["id"] == 7
        assert "inferred_schema" not in item
        assert "field_mapping" not in item
        assert "staged_metadata" not in item

    asyncio.run(_run())
