"""Product Master gap worklist pagination — skip/limit envelope (no cip)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.imports.product_master_gap_worklist import product_master_gap_worklist


def _row(token: str, *, occurrence_count: int = 1) -> dict:
    return {
        "token": token,
        "sources": ["shipment"],
        "status": "unresolved",
        "resolution_statuses": ["no_match"],
        "occurrence_count": occurrence_count,
        "quantity_impact": 0.0,
        "sample_identifiers": token,
        "first_seen": None,
        "last_seen": None,
        "affected_job_ids": [],
        "deep_link": {"href": "/admin/imports", "label": "Import center"},
    }


async def _seed_merge(_db, rows_by_token: dict) -> None:
    for i in range(10):
        token = f"TOK{i:02d}"
        rows_by_token[token] = _row(token, occurrence_count=10 - i)


@pytest.fixture
def client():
    return TestClient(app)


def test_worklist_skip_limit_window():
    db = AsyncMock()
    with (
        patch(
            "app.services.imports.product_master_gap_worklist._merge_shipment_tokens",
            new=AsyncMock(side_effect=_seed_merge),
        ),
        patch("app.services.imports.product_master_gap_worklist._merge_dsi_tokens", new=AsyncMock()),
        patch("app.services.imports.product_master_gap_worklist._merge_cpor_claim_tokens", new=AsyncMock()),
    ):
        out = asyncio.run(product_master_gap_worklist(db, skip=2, limit=3))

    assert out["total"] == 10
    assert out["skip"] == 2
    assert out["limit"] == 3
    assert [r["token"] for r in out["rows"]] == ["TOK02", "TOK03", "TOK04"]


def test_worklist_total_independent_of_page():
    db = AsyncMock()
    with (
        patch(
            "app.services.imports.product_master_gap_worklist._merge_shipment_tokens",
            new=AsyncMock(side_effect=_seed_merge),
        ),
        patch("app.services.imports.product_master_gap_worklist._merge_dsi_tokens", new=AsyncMock()),
        patch("app.services.imports.product_master_gap_worklist._merge_cpor_claim_tokens", new=AsyncMock()),
    ):
        out = asyncio.run(product_master_gap_worklist(db, skip=50, limit=10))

    assert out["total"] == 10
    assert out["rows"] == []


def test_worklist_endpoint_envelope(client: TestClient):
    payload = {
        "rows": [_row("A")],
        "total": 42,
        "skip": 25,
        "limit": 25,
        "status_vocabulary": {},
        "data_unavailable": False,
    }
    with patch(
        "app.api.v1.endpoints.product_master_gaps.product_master_gap_worklist",
        new=AsyncMock(return_value=payload),
    ):
        res = client.get("/api/v1/product-master-gaps/worklist?skip=25&limit=25")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 42
    assert body["skip"] == 25
    assert body["limit"] == 25
    assert len(body["rows"]) == 1
    assert "truncated" not in body


def test_worklist_limit_ceiling_rejected(client: TestClient):
    res = client.get("/api/v1/product-master-gaps/worklist?limit=501")
    assert res.status_code == 422
