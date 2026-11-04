"""N-0100: full-customer merge preview, bulk preview and confirm require steward.

Admin still passes. Planner and viewer are refused. Alias-scope merge stays ungated.
Confirm is not dispatched; the enqueue function is replaced so this test does not merge
rows. cip_test only.
"""

from __future__ import annotations

import secrets

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.security import Role
from app.db.session_sync import SessionLocal
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.main import app
from app.models.dimensions import DimCustomer
from app.services.imports.dsi_customer_name_normalization import (
    normalize_customer_name_for_similarity,
)

PREVIEW = "/api/v1/customers/duplicate-groups/merge-preview"
BULK = "/api/v1/customers/duplicate-groups/merge-preview-bulk"
CONFIRM = "/api/v1/customers/duplicate-groups/merge-confirm"
ALIAS_PREVIEW = "/api/v1/customers/alias-scope-conflicts/merge-preview"
ALIAS_CONFIRM = "/api/v1/customers/alias-scope-conflicts/merge-confirm"
_REQUIRE_ROLES_DEP_QUALNAME = "require_roles.<locals>._dep"
NOTE = "n0100 steward role check"


def _require_cip_test() -> None:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    try:
        with engine.connect() as conn:
            name = conn.execute(text("select current_database()")).scalar()
    finally:
        engine.dispose()
    if name != "cip_test":
        pytest.skip("cip_test only")


def _headers(role: str) -> dict[str, str]:
    return {"X-User-Role": role, "X-User-Id": f"n0100-{role}-probe"}


def _dependant_calls(dependant) -> list:
    found: list = []
    stack = [dependant]
    while stack:
        dep = stack.pop()
        if dep is None:
            continue
        call = getattr(dep, "call", None)
        if call is not None:
            found.append(call)
        stack.extend(getattr(dep, "dependencies", None) or [])
    return found


def _allowed_roles(route: APIRoute) -> frozenset[Role] | None:
    for call in _dependant_calls(route.dependant):
        if getattr(call, "__qualname__", "") != _REQUIRE_ROLES_DEP_QUALNAME:
            continue
        for cell in call.__closure__ or ():
            if isinstance(cell.cell_contents, set):
                return frozenset(cell.cell_contents)
    return None


def _route(method: str, path: str) -> APIRoute:
    matches = [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and r.path == path and method in (r.methods or ())
    ]
    assert len(matches) == 1, path
    return matches[0]


def test_full_merge_routes_require_steward_and_alias_scope_does_not() -> None:
    steward = frozenset({Role.STEWARD})
    assert _allowed_roles(_route("POST", PREVIEW)) == steward
    assert _allowed_roles(_route("POST", BULK)) == steward
    assert _allowed_roles(_route("POST", CONFIRM)) == steward
    assert _allowed_roles(_route("POST", ALIAS_PREVIEW)) is None
    assert _allowed_roles(_route("POST", ALIAS_CONFIRM)) is None


@pytest.fixture
def pair():
    _require_cip_test()
    token = secrets.token_hex(4)
    name_a = f"N0100 Merge Probe {token}"
    name_b = f"N0100 Merge Probe {token} (Pty) Ltd"
    key = normalize_customer_name_for_similarity(name_a)
    assert key and key == normalize_customer_name_for_similarity(name_b)
    ids: list[int] = []
    with SessionLocal() as session:
        rows = [
            DimCustomer(code=f"C-N0100-A-{token}", name=name_a, customer_status="active"),
            DimCustomer(code=f"C-N0100-B-{token}", name=name_b, customer_status="unverified"),
        ]
        session.add_all(rows)
        session.commit()
        ids = [int(rows[0].id), int(rows[1].id)]
    try:
        yield {"survivor_id": ids[0], "loser_id": ids[1], "similarity_key": key}
    finally:
        with SessionLocal() as session:
            for customer_id in ids:
                row = session.get(DimCustomer, customer_id)
                if row is not None:
                    session.delete(row)
            session.commit()


@pytest.fixture
def client():
    _require_cip_test()
    with TestClient(app) as http:
        yield http


def _preview_body(pair: dict) -> dict:
    return {
        "similarity_key": pair["similarity_key"],
        "survivor_id": pair["survivor_id"],
        "audit_note": NOTE,
    }


def _bulk_body(pair: dict) -> dict:
    return {"groups": [_preview_body(pair)], "audit_note": NOTE}


def test_steward_and_admin_preview_and_confirm_succeed(
    client: TestClient, pair: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict] = []

    def _enqueue(payload: dict) -> tuple[str, bool]:
        captured.append(payload)
        return "n0100-task", True

    monkeypatch.setattr(
        "app.services.customer_full_merge_enqueue.enqueue_customer_full_merge_confirm",
        _enqueue,
    )
    for role in ("steward", "admin"):
        preview = client.post(PREVIEW, json=_preview_body(pair), headers=_headers(role))
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["dry_run"] is True
        assert body["survivor_id"] == pair["survivor_id"]
        assert pair["loser_id"] in body["loser_ids"]

        bulk = client.post(BULK, json=_bulk_body(pair), headers=_headers(role))
        assert bulk.status_code == 200, bulk.text
        assert bulk.json()["group_count"] == 1

        confirmed = client.post(CONFIRM, json=_preview_body(pair), headers=_headers(role))
        assert confirmed.status_code == 202, confirmed.text
        assert confirmed.json()["task_id"] == "n0100-task"
        assert confirmed.json()["async_poll"] is True

    assert [row["performed_by"] for row in captured] == ["n0100-steward-probe", "n0100-admin-probe"]
    assert all(row["survivor_id"] == pair["survivor_id"] for row in captured)


@pytest.mark.parametrize("role", ["planner", "viewer"])
def test_planner_and_viewer_are_refused(client: TestClient, role: str) -> None:
    headers = _headers(role)
    body = {"similarity_key": "n0100-no-such-group", "survivor_id": 1, "audit_note": NOTE}
    bulk = {"groups": [body], "audit_note": NOTE}
    for path, payload in ((PREVIEW, body), (BULK, bulk), (CONFIRM, body)):
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "Insufficient role"
