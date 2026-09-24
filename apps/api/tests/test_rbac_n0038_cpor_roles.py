"""N-0038 (BACKLOG-136 / BACKLOG-141) — CPOR write role matrix and shipment steward gates.

No database access: route introspection, plus TestClient calls with get_current_user / DB
dependencies overridden. Allowed-role requests use an invalid path parameter so they stop at
422 validation (after the role check has passed) and never reach a handler or SessionLocal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.v1.endpoints.cpor_payment_evidence import _sync_db
from app.core.security import Role, get_current_user
from app.main import app

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REQUIRE_ROLES_DEP_QUALNAME = "require_roles.<locals>._dep"

_PLANNER = frozenset({Role.PLANNER, Role.ADMIN})
_STEWARD_PLANNER = frozenset({Role.STEWARD, Role.PLANNER, Role.ADMIN})
_ADMIN = frozenset({Role.ADMIN})
_SHIPMENT_STEWARD = frozenset({Role.ADMIN, Role.STEWARD})

_P = "/api/v1/cpor"

# The role matrix (IMPL.md N-0038). Every CPOR write route must appear here with its allowed set.
_CPOR_WRITE_MATRIX: dict[tuple[str, str], frozenset[Role]] = {
    # cpor_cases.py — case lifecycle / settle / claim evidence / promo plan
    ("POST", f"{_P}/cases"): _PLANNER,
    ("PATCH", f"{_P}/cases/{{case_id}}"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/intelligence-exclude"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/supersede/preview"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/supersede"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/supersede/restore"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/lines"): _PLANNER,
    ("PATCH", f"{_P}/cases/{{case_id}}/lines/{{line_id}}"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/lines/{{line_id}}/void"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/lines/{{line_id}}/split-layers"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/recompute"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/transition"): _PLANNER,
    ("POST", f"{_P}/intelligence/promo-plan-draft/recompute"): _PLANNER,
    ("POST", f"{_P}/intelligence/promo-plan-draft/create-case"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/claim-evidence/import"): _PLANNER,
    ("POST", f"{_P}/cases/{{case_id}}/settlement/rollup"): _PLANNER,
    # cpor_exports.py
    ("POST", f"{_P}/cases/{{case_id}}/export"): _PLANNER,
    # cpor_fx.py
    ("POST", f"{_P}/fx/rates/fetch"): _PLANNER,
    ("POST", f"{_P}/fx/backfill-confirm"): _PLANNER,
    ("POST", f"{_P}/fx/declare-mode"): _PLANNER,
    # cpor_historical_import.py — ADMIN-only (BACKLOG-136 regression trap: equivalent or stronger)
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/map-token"): _ADMIN,
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/bulk-map-token"): _ADMIN,
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/validate"): _ADMIN,
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/apply"): _ADMIN,
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/resolution-plan"): _ADMIN,
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/resolution-plan/compute-async"): _ADMIN,
    ("POST", f"{_P}/historical-import/jobs/{{job_id}}/resolution-plan/apply-async"): _ADMIN,
    # cpor_payment_evidence.py — data-steward work
    ("POST", f"{_P}/payment-evidence/jobs/{{job_id}}/map-token"): _STEWARD_PLANNER,
    ("POST", f"{_P}/payment-evidence/jobs/{{job_id}}/mark-shell-case"): _STEWARD_PLANNER,
    ("POST", f"{_P}/payment-evidence/jobs/{{job_id}}/re-resolve"): _STEWARD_PLANNER,
    ("POST", f"{_P}/payment-evidence/jobs/{{job_id}}/apply"): _STEWARD_PLANNER,
}


def _dependant_calls(dependant) -> list:
    found: list = []
    if dependant is None:
        return found
    call = getattr(dependant, "call", None)
    if call is not None:
        found.append(call)
    for dep in getattr(dependant, "dependencies", None) or []:
        found.extend(_dependant_calls(dep))
    return found


def _allowed_roles(route: APIRoute) -> frozenset[Role] | None:
    """The allowed set captured by require_roles(...) on this route, or None when ungated."""
    for call in _dependant_calls(route.dependant):
        if getattr(call, "__qualname__", "") != _REQUIRE_ROLES_DEP_QUALNAME:
            continue
        for cell in call.__closure__ or ():
            if isinstance(cell.cell_contents, set):
                return frozenset(cell.cell_contents)
    return None


def _route_key(route: APIRoute) -> tuple[str, str]:
    methods = sorted(m for m in (route.methods or ()) if m not in {"HEAD", "OPTIONS"})
    return (methods[0] if methods else "", route.path)


def _cpor_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(f"{_P}/")]


def test_every_cpor_write_route_matches_the_role_matrix():
    seen: dict[tuple[str, str], frozenset[Role] | None] = {}
    for route in _cpor_routes():
        if not (set(route.methods or ()) & _WRITE_METHODS):
            continue
        seen[_route_key(route)] = _allowed_roles(route)
    ungated = sorted(k for k, v in seen.items() if v is None)
    assert ungated == [], f"CPOR write routes without require_roles: {ungated}"
    unlisted = sorted(set(seen) - set(_CPOR_WRITE_MATRIX))
    assert unlisted == [], f"new CPOR write route missing from the N-0038 matrix: {unlisted}"
    missing = sorted(set(_CPOR_WRITE_MATRIX) - set(seen))
    assert missing == [], f"matrix routes not mounted: {missing}"
    wrong = {k: sorted(r.value for r in seen[k]) for k in seen if seen[k] != _CPOR_WRITE_MATRIX[k]}
    assert wrong == {}, f"CPOR write routes with the wrong allowed set: {wrong}"


def test_no_cpor_write_admits_viewer():
    for key, allowed in _CPOR_WRITE_MATRIX.items():
        assert Role.VIEWER not in allowed, key


def test_cpor_reads_stay_authentication_only():
    gated_reads = [
        _route_key(r)
        for r in _cpor_routes()
        if "GET" in (r.methods or ()) and _allowed_roles(r) is not None
    ]
    assert gated_reads == [], f"CPOR GETs must stay readable by viewer: {gated_reads}"


def test_shipment_evidence_gates_admit_steward_and_admin():
    gated = {
        _route_key(r): _allowed_roles(r)
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/v1/shipment-evidence")
    }
    gated = {k: v for k, v in gated.items() if v is not None}
    assert len(gated) == 25
    wrong = {k: v for k, v in gated.items() if v != _SHIPMENT_STEWARD}
    assert wrong == {}, f"shipment steward gates must be ADMIN+STEWARD: {wrong}"


# --- behaviour through the real dependency chain ------------------------------------------------


def _mock_db():
    yield MagicMock()


@pytest.fixture
def as_role():
    role_box: dict[str, Role] = {}

    def override_user() -> dict:
        return {
            "id": f"n0038-{role_box['role'].value}",
            "role": role_box["role"],
            "email": None,
            "tenant_id": "default",
            "display_name": None,
        }

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = _mock_db
    app.dependency_overrides[_sync_db] = _mock_db
    client = TestClient(app)

    def _client(role: Role) -> TestClient:
        role_box["role"] = role
        return client

    try:
        yield _client
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(_sync_db, None)


# (method, url with an invalid int path param or body, allowed role, denied roles)
_BEHAVIOUR_CASES = [
    ("POST", f"{_P}/cases/not-an-int/transition", {"action": "approve"}, Role.PLANNER, [Role.VIEWER, Role.STEWARD]),
    ("PATCH", f"{_P}/cases/not-an-int", {}, Role.PLANNER, [Role.VIEWER]),
    ("POST", f"{_P}/cases/not-an-int/export", None, Role.PLANNER, [Role.VIEWER, Role.STEWARD]),
    ("POST", f"{_P}/cases/not-an-int/settlement/rollup", None, Role.PLANNER, [Role.VIEWER]),
    ("POST", f"{_P}/fx/backfill-confirm", {"items": []}, Role.PLANNER, [Role.VIEWER, Role.STEWARD]),
    ("POST", f"{_P}/fx/declare-mode", {"case_ids": "x"}, Role.PLANNER, [Role.VIEWER]),
    ("POST", f"{_P}/historical-import/jobs/not-an-int/apply", {}, Role.ADMIN, [Role.VIEWER, Role.PLANNER, Role.STEWARD]),
    ("POST", f"{_P}/payment-evidence/jobs/not-an-int/apply", {"confirm": True}, Role.STEWARD, [Role.VIEWER]),
    ("POST", f"{_P}/payment-evidence/jobs/not-an-int/map-token", {}, Role.PLANNER, [Role.VIEWER]),
    (
        "POST",
        "/api/v1/shipment-evidence/jobs/not-an-int/apply",
        {},
        Role.STEWARD,
        [Role.VIEWER, Role.PLANNER],
    ),
    ("GET", "/api/v1/shipment-evidence/not-an-int", None, Role.STEWARD, [Role.VIEWER, Role.PLANNER]),
]


@pytest.mark.parametrize("method,url,body,allowed,denied", _BEHAVIOUR_CASES)
def test_allowed_role_passes_gate_and_denied_role_gets_403(as_role, method, url, body, allowed, denied):
    kwargs = {"json": body} if body is not None else {}
    ok = as_role(allowed).request(method, url, **kwargs)
    # 422 = the role check passed and path/body validation stopped the request before any handler.
    assert ok.status_code == 422, (allowed, ok.status_code, ok.text)
    for role in denied:
        r = as_role(role).request(method, url, **kwargs)
        assert r.status_code == 403, (role, r.status_code, r.text)
        assert r.json()["detail"] == "Insufficient role"


def test_admin_passes_every_gate(as_role):
    r = as_role(Role.ADMIN).post(f"{_P}/cases/not-an-int/transition", json={"action": "approve"})
    assert r.status_code == 422, r.text
    r = as_role(Role.ADMIN).post(f"{_P}/payment-evidence/jobs/not-an-int/apply", json={"confirm": True})
    assert r.status_code == 422, r.text


def test_viewer_can_still_read_cpor(as_role):
    # Read route: viewer is not refused by a role gate (422 on the bad id, not 403).
    r = as_role(Role.VIEWER).get(f"{_P}/cases/not-an-int")
    assert r.status_code == 422, r.text
