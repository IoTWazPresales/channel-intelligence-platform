"""GET /imports/jobs list performance contract (lightweight columns + pagination)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.api.v1.endpoints.imports import list_jobs


def test_list_jobs_returns_paginated_items_without_jsonb_blobs(monkeypatch) -> None:
    import app.services.imports.import_load_report as load_report

    async def _reports(_db, jobs):
        # N-0111: the list reads per-reason staging counts in one grouped query per template.
        assert [j for j, _slug in jobs] == [7]
        return {7: load_report.build_report("distributor_inventory", {"loaded": 3, "no_date": 2})}

    monkeypatch.setattr(load_report, "load_reports_async", _reports)

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

        out = await list_jobs(db=db, include_archived=False, limit=50, offset=0, user=None)

        assert out["total"] == 1
        assert out["limit"] == 50
        assert len(out["items"]) == 1
        item = out["items"][0]
        assert item["id"] == 7
        assert "inferred_schema" not in item
        assert "field_mapping" not in item
        assert "staged_metadata" not in item
        assert item["display_status"] == "Completed with rows not loaded (2)"
        assert (item["rows_read"], item["rows_loaded"], item["rows_not_loaded"]) == (5, 3, 2)

    asyncio.run(_run())
