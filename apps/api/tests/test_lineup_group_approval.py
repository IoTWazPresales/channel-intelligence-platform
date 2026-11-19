"""Final wave (b): POST /lineup/items/group-approval approves or rejects one customer's period."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.deps import get_db
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
URL = "/api/v1/lineup/items/group-approval"


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _row(item_id: int, status: str) -> MagicMock:
    row = MagicMock()
    row.id = item_id
    row.approval_status = status
    return row


def _session(rows: list) -> list:
    holder: list = []

    async def fake_db():
        sess = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        sess.execute = AsyncMock(return_value=result)
        sess.flush = AsyncMock()
        sess.run_sync = AsyncMock()
        sess.commit = AsyncMock()
        holder.append(sess)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    return holder


def test_approves_only_pending_items_with_one_ledger_draw_and_event_each():
    rows = [_row(1, "draft"), _row(2, "pending_approval"), _row(3, "rejected"), _row(4, "approved")]
    holder = _session(rows)
    with patch(
        "app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock
    ) as audit:
        r = client.post(
            URL,
            json={
                "customer_id": 5,
                "period_start": "2026-01-01",
                "approval_status": "approved",
                "notes": " ok ",
            },
            headers={"X-User-Id": "reviewer-1"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed_ids"] == [1, 2] and body["changed"] == 2 and body["unchanged"] == 2
    assert [row.approval_status for row in rows] == ["approved", "approved", "rejected", "approved"]
    assert holder[0].run_sync.await_count == 2
    assert audit.await_count == 2
    first = audit.await_args_list[0].kwargs
    assert first == {
        "lineup_item_id": 1,
        "old_status": "draft",
        "new_status": "approved",
        "notes": "ok",
        "actor": "reviewer-1",
    }
    holder[0].commit.assert_awaited_once()


def test_only_pending_false_also_changes_decided_items():
    rows = [_row(1, "approved"), _row(2, "draft"), _row(3, "rejected")]
    holder = _session(rows)
    with patch(
        "app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock
    ) as audit:
        r = client.post(
            URL,
            json={
                "customer_id": 5,
                "period_start": "2026-01-01",
                "approval_status": "rejected",
                "only_pending": False,
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["changed_ids"] == [1, 2]
    assert [row.approval_status for row in rows] == ["rejected", "rejected", "rejected"]
    assert audit.await_count == 2
    assert holder[0].run_sync.await_count == 2


def test_unknown_customer_period_is_404_and_writes_nothing():
    holder = _session([])
    r = client.post(
        URL, json={"customer_id": 5, "period_start": "2026-01-01", "approval_status": "approved"}
    )
    assert r.status_code == 404
    holder[0].commit.assert_not_awaited()


def test_only_approved_or_rejected_is_accepted():
    _session([_row(1, "draft")])
    r = client.post(
        URL, json={"customer_id": 5, "period_start": "2026-01-01", "approval_status": "draft"}
    )
    assert r.status_code == 422


def test_route_is_published():
    paths = client.get("/openapi.json").json()["paths"]
    assert URL in paths
