"""Approval audit on PATCH /lineup/items/{id}."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.security import Role, get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    # PATCH takes its actor from the authenticated user, never from the X-User-Id header.
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "reviewer-1",
        "role": Role.ADMIN,
        "tenant_id": "default",
        "email": None,
        "display_name": None,
    }
    yield
    app.dependency_overrides.clear()


def test_patch_approval_change_invokes_audit_writer():
    row = MagicMock()
    row.id = 7
    row.approval_status = "draft"
    row.notes = None

    holder: list = []

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=row)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        # N-0079: an approval change flushes, then draws the budget ledger through run_sync.
        sess.flush = AsyncMock()
        sess.run_sync = AsyncMock()
        holder.append(sess)
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch("app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock) as audit:
        r = client.patch(
            "/api/v1/lineup/items/7",
            json={"approval_status": "approved", "notes": "LGTM"},
            headers={"X-User-Id": "forged-by-client"},
        )
    assert r.status_code == 200
    audit.assert_awaited_once()
    holder[0].run_sync.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["lineup_item_id"] == 7
    assert kwargs["old_status"] == "draft"
    assert kwargs["new_status"] == "approved"
    assert kwargs["notes"] == "LGTM"
    # The authenticated user, not the forged header.
    assert kwargs["actor"] == "reviewer-1"


def test_patch_same_approval_skips_audit():
    row = MagicMock()
    row.id = 3
    row.approval_status = "draft"
    row.notes = "x"

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=row)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db

    with patch("app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock) as audit:
        r = client.patch("/api/v1/lineup/items/3", json={"approval_status": "draft"})
    assert r.status_code == 200
    audit.assert_not_called()
