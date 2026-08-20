"""RBAC R1 — CPOR write routes must authenticate; actor is non-null from the user payload.

No database access: route introspection + pure `_actor()` calls only.
"""

from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.v1.endpoints.cpor_cases import _actor as cases_actor
from app.api.v1.endpoints.cpor_exports import _actor as exports_actor
from app.core.security import Role, get_current_user
from app.main import app

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _dependant_calls(dependant) -> set:
    found: set[object] = set()
    if dependant is None:
        return found
    call = getattr(dependant, "call", None)
    if call is not None:
        found.add(call)
    for dep in getattr(dependant, "dependencies", None) or []:
        found |= _dependant_calls(dep)
    return found


def _is_cpor_path(path: str) -> bool:
    return "/cpor/" in path or path.rstrip("/").endswith("/cpor")


def test_actor_non_null_for_stub_mode_user_payload():
    user = {"id": "demo-user", "role": Role.ADMIN, "email": None}
    assert cases_actor(user) == "demo-user"
    assert exports_actor(user) == "demo-user"


def test_all_cpor_write_routes_depend_on_get_current_user():
    missing: list[tuple[str, str]] = []
    writes: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = route.path
        if not _is_cpor_path(path):
            continue
        methods = set(route.methods or ())
        if not (methods & _WRITE_METHODS):
            continue
        writes.append(path)
        if get_current_user not in _dependant_calls(route.dependant):
            missing.append((",".join(sorted(methods)), path))
    assert writes, "expected CPOR write routes to be mounted"
    assert missing == [], f"CPOR write routes missing get_current_user: {missing}"


def test_sync_cpor_writes_resolve_async_get_current_user():
    """Several CPOR writes are sync `def`; FastAPI still injects async get_current_user."""
    assert inspect.iscoroutinefunction(get_current_user)
    sync_authenticated: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_cpor_path(route.path):
            continue
        if not (set(route.methods or ()) & _WRITE_METHODS):
            continue
        if inspect.iscoroutinefunction(route.endpoint):
            continue
        if get_current_user in _dependant_calls(route.dependant):
            sync_authenticated.append(route.path)
    assert sync_authenticated, "expected at least one sync CPOR write with get_current_user"


def test_sync_write_route_responds_with_get_current_user():
    """Sync ``def`` transition still responds when get_current_user is the async dependency."""

    def override_user() -> dict:
        return {"id": "demo-user", "role": Role.ADMIN, "email": None, "tenant_id": "default"}

    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)
    case = SimpleNamespace(
        id=10,
        status="draft",
        customer_id=1,
        case_code="X",
        case_name=None,
        promotion_type="Sell out PP",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 7),
        roe_snapshot=None,
        currency_code="ZAR",
        channel="reseller",
        notes=None,
        created_by=None,
        export_version=1,
        workflow_status="draft",
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
        superseded_by_case_id=None,
        created_at=None,
    )
    session = MagicMock()
    session.get = MagicMock(return_value=case)
    try:
        with patch("app.api.v1.endpoints.cpor_cases.SessionLocal") as sl:
            sl.return_value.__enter__.return_value = session
            sl.return_value.__exit__.return_value = None
            response = client.post("/api/v1/cpor/cases/10/transition", json={"action": "approve"})
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["current"] == "draft"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
