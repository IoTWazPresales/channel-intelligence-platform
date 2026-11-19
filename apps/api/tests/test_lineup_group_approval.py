"""Final wave (b): POST /lineup/items/group-approval approves or rejects one customer's period."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.deps import get_db
from app.core.security import Role, get_current_user
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
URL = "/api/v1/lineup/items/group-approval"


@pytest.fixture(autouse=True)
def clear_overrides():
    # Group approval takes its actor from the authenticated user, never from a header.
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "reviewer-1",
        "role": Role.ADMIN,
        "tenant_id": "default",
        "email": None,
        "display_name": None,
    }
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


def test_actor_is_the_authenticated_user_not_the_x_user_id_header():
    rows = [_row(1, "draft")]
    _session(rows)
    with patch(
        "app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock
    ) as audit:
        r = client.post(
            URL,
            json={"customer_id": 5, "period_start": "2026-01-01", "approval_status": "approved"},
            headers={"X-User-Id": "forged-by-client"},
        )
    assert r.status_code == 200, r.text
    assert audit.await_args.kwargs["actor"] == "reviewer-1"


def test_ledger_actor_is_the_authenticated_user_too():
    rows = [_row(1, "draft")]
    holder = _session(rows)
    seen = {}

    def fake_apply(sync, item, prev, new, actor=None):
        seen["actor"] = actor
        return 0

    with (
        patch("app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock),
        patch("app.services.budget_ledger.apply_lineup_approval", fake_apply),
    ):
        r = client.post(
            URL,
            json={"customer_id": 5, "period_start": "2026-01-01", "approval_status": "approved"},
            headers={"X-User-Id": "forged-by-client"},
        )
        assert r.status_code == 200, r.text
        # run_sync is a mock on the fake session; run the callback it was given
        callback = holder[0].run_sync.await_args.args[0]
        callback(MagicMock())
    assert seen["actor"] == "reviewer-1"


def test_items_are_selected_with_a_row_lock_and_fresh_state():
    """Two approvers must serialize on the rows, and the status check must read the locked row."""
    rows = [_row(1, "draft")]
    holder = _session(rows)
    with patch("app.api.v1.endpoints.lineup.record_lineup_approval_event", new_callable=AsyncMock):
        r = client.post(
            URL,
            json={"customer_id": 5, "period_start": "2026-01-01", "approval_status": "approved"},
        )
    assert r.status_code == 200, r.text
    stmt = holder[0].execute.await_args_list[0].args[0]
    assert stmt._for_update_arg is not None, "group approval must lock the items it changes"
    assert stmt.get_execution_options().get("populate_existing") is True


def test_patch_locks_the_item_it_changes():
    holder: list = []

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=None)
        holder.append(sess)
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch("/api/v1/lineup/items/9", json={"approval_status": "approved"})
    assert r.status_code == 404
    assert holder[0].get.await_args.kwargs.get("with_for_update") is True
