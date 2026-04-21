"""Line-up planning API (PATCH approval workflow)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_patch_lineup_item_updates_approval_status():
    row = MagicMock()
    row.id = 10
    row.approval_status = "draft"
    row.notes = None

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=row)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db

    r = client.patch("/api/v1/lineup/items/10", json={"approval_status": "pending_approval"})
    assert r.status_code == 200
    assert r.json() == {"id": 10, "approval_status": "pending_approval", "notes": None}
    assert row.approval_status == "pending_approval"


def test_patch_lineup_item_rejects_invalid_status():
    row = MagicMock()
    row.id = 1
    row.approval_status = "draft"
    row.notes = None

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=row)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db

    r = client.patch("/api/v1/lineup/items/1", json={"approval_status": "bogus"})
    assert r.status_code == 400


def test_patch_lineup_item_404_when_missing():
    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=None)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    r = client.patch("/api/v1/lineup/items/999", json={"approval_status": "approved"})
    assert r.status_code == 404
