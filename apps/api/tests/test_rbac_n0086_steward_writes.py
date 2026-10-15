"""N-0086 — steward writes on the import / steward routers need steward or admin.

No database access: route introspection, plus TestClient calls with get_current_user / get_db
overridden. A denied role is refused by the require_roles dependency before any handler runs (403).
An allowed role is only exercised on routes with an integer path parameter, sent as "not-an-int",
so the request stops at 422 validation after the role check and never reaches a handler.

The matrix below is the after-state list from .eif/audit/PROGRAMME_20261009/N0086_IMPL.md.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.v1.endpoints.imports import (
    PLANNER_RUN_TEMPLATES,
    PLANNER_UPLOAD_TEMPLATES,
    require_import_template_role,
)
from app.core.security import Role, get_current_user
from app.main import app

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REQUIRE_ROLES_DEP_QUALNAME = "require_roles.<locals>._dep"

_STEWARD = frozenset({Role.ADMIN, Role.STEWARD})
_RUNNER = frozenset({Role.ADMIN, Role.STEWARD, Role.PLANNER})
_ADMIN = frozenset({Role.ADMIN})

_PREFIXES = (
    "/api/v1/imports",
    "/api/v1/cst-steward",
    "/api/v1/mappings",
    "/api/v1/product-master-gaps",
    "/api/v1/exceptions",
)

_I = "/api/v1/imports"
_C = "/api/v1/cst-steward"
_M = "/api/v1/mappings"

# Every write route under _PREFIXES with its allowed set (admin always passes require_roles).
_WRITE_MATRIX: dict[tuple[str, str], frozenset[Role]] = {
    # imports.py — pre-existing admin-only bulk delete
    ("POST", f"{_I}/jobs/bulk-delete-preview"): _ADMIN,
    ("POST", f"{_I}/jobs/bulk-delete-confirm"): _ADMIN,
    # imports.py — job runner: planner admitted at the route, then checked per template
    ("POST", f"{_I}/jobs"): _RUNNER,
    ("POST", f"{_I}/jobs/{{job_id}}/cancel"): _RUNNER,
    ("POST", f"{_I}/jobs/{{job_id}}/retry"): _RUNNER,
    ("POST", f"{_I}/jobs/{{job_id}}/process"): _RUNNER,
    # imports.py — steward writes (N-0086)
    ("POST", f"{_I}/jobs/{{job_id}}/dsi-file-exclusions"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/dsi-file-distributors"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/dsi-file-snapshot-periods"): _STEWARD,
    ("POST", f"{_I}/dsi/batch-propose"): _STEWARD,
    ("POST", f"{_I}/dsi/batch-jobs"): _STEWARD,
    ("POST", f"{_I}/cst/batch-propose"): _STEWARD,
    ("POST", f"{_I}/cst/batch-jobs"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-confirm-year"): _STEWARD,  # N-0111
    ("POST", f"{_I}/jobs/{{job_id}}/shipment-sheets"): _STEWARD,
    ("PUT", f"{_I}/jobs/{{job_id}}/shipment-field-mapping"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/shipment-validate"): _STEWARD,
    ("PUT", f"{_I}/jobs/{{job_id}}/dsi-field-mapping"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/dsi-validate"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/dsi-apply"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-candidates/{{candidate_id}}/resolve"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-candidates/{{candidate_id}}/ignore"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-steward-bulk-preview"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-steward-bulk-apply"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-steward-bulk-ignore/apply-async"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-steward-bulk-provisional-customers/apply-async"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-resolution-plan"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-resolution-plan/compute-async"): _STEWARD,
    ("POST", f"{_I}/jobs/{{job_id}}/cst-resolution-plan/apply-async"): _STEWARD,
    # imports_product_master.py — pre-existing admin-only
    ("POST", f"{_I}/product-master/jobs"): _ADMIN,
    ("PUT", f"{_I}/product-master/jobs/{{job_id}}/mapping"): _ADMIN,
    ("POST", f"{_I}/product-master/jobs/{{job_id}}/validate"): _ADMIN,
    ("POST", f"{_I}/product-master/jobs/{{job_id}}/commit"): _ADMIN,
    # cst_steward.py
    ("PATCH", f"{_C}/key-accounts/{{customer_id}}"): _STEWARD,
    ("POST", f"{_C}/report-slots/advance"): _STEWARD,
    ("POST", f"{_C}/p4-bootstrap-configs"): _ADMIN,
    ("POST", f"{_C}/article-aliases/import"): _STEWARD,
    ("POST", f"{_C}/article-aliases/confirm-import"): _STEWARD,
    ("PATCH", f"{_C}/article-aliases/{{alias_id}}"): _STEWARD,
    ("POST", f"{_C}/article-aliases/derive-eras-from-shipping"): _STEWARD,
    ("POST", f"{_C}/article-aliases/confirm-shipping-derived"): _STEWARD,
    ("POST", f"{_C}/article-aliases/reresolve-job-residuals"): _STEWARD,
    ("POST", f"{_C}/article-aliases/{{alias_id}}/confirm"): _STEWARD,
    ("POST", f"{_C}/article-aliases/{{alias_id}}/reject"): _STEWARD,
    # N-0110 stock gap: the on-hand threshold setting and the recompute are steward writes
    ("PUT", f"{_C}/stock-gap/settings"): _STEWARD,
    ("POST", f"{_C}/stock-gap/recompute"): _STEWARD,
    # mappings.py
    ("POST", f"{_M}/queue/{{item_id}}/approve"): _STEWARD,
    ("POST", f"{_M}/queue/{{item_id}}/reject"): _STEWARD,
    ("DELETE", f"{_M}/queue/{{item_id}}"): _STEWARD,
    ("POST", f"{_M}/queue/clear-all"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/resolve-product"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/map-customer"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/duplicate-review/different-entity"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/duplicate-review/same-entity"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/duplicate-review/cluster-same-entity"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/create-provisional-customer"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/mark-open-channel"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/ignore"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/map-distributor"): _STEWARD,
    ("POST", f"{_M}/import-candidates/{{candidate_id}}/create-provisional-distributor"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-steward-bulk-preview"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-steward-bulk-provisional-customers/apply-async"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-steward-bulk-ignore/apply-async"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-steward-bulk-apply"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-resolution-plan/compute-async"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-resolution-plan"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-resolution-plan/effective"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-resolution-plan/apply-async"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-resolution-plan/apply"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-apply-complete"): _ADMIN,
    ("POST", f"{_M}/import-jobs/{{job_id}}/revalidate-distributor-sales-inventory"): _STEWARD,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-geo-steward/channel-create"): _ADMIN,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-geo-steward/channel-alias"): _ADMIN,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-geo-steward/region-create"): _ADMIN,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-geo-steward/region-alias"): _ADMIN,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-geo-steward/region-register-from-hint"): _ADMIN,
    ("POST", f"{_M}/import-jobs/{{job_id}}/dsi-geo-steward/bulk-apply"): _ADMIN,
    ("POST", f"{_M}/customer-source-token-aliases"): _STEWARD,
    # product_master_gaps.py (preview is read-only server-side; gated with the apply it precedes)
    ("POST", "/api/v1/product-master-gaps/scan"): _STEWARD,
    ("POST", "/api/v1/product-master-gaps/preview"): _STEWARD,
    ("POST", "/api/v1/product-master-gaps/apply"): _STEWARD,
    # exceptions.py
    ("DELETE", "/api/v1/exceptions/{item_id}"): _STEWARD,
    ("POST", "/api/v1/exceptions/clear-all"): _STEWARD,
}

# Reads that were already role-gated before N-0086 (everything else stays sign-in only).
_GATED_READS = {("GET", f"{_I}/product-master/jobs/{{job_id}}/state"): _ADMIN}


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
    """The strictest allowed set captured by require_roles(...) on this route, or None when ungated."""
    sets = []
    for call in _dependant_calls(route.dependant):
        if getattr(call, "__qualname__", "") != _REQUIRE_ROLES_DEP_QUALNAME:
            continue
        for cell in call.__closure__ or ():
            if isinstance(cell.cell_contents, set):
                sets.append(frozenset(cell.cell_contents))
    if not sets:
        return None
    return min(sets, key=len)


def _route_key(route: APIRoute) -> tuple[str, str]:
    methods = sorted(m for m in (route.methods or ()) if m not in {"HEAD", "OPTIONS"})
    return (methods[0] if methods else "", route.path)


def _scoped_routes() -> list[APIRoute]:
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and any(r.path == p or r.path.startswith(p + "/") for p in _PREFIXES)
    ]


# --- the matrix ------------------------------------------------------------------------------


def test_every_steward_router_write_matches_the_matrix():
    seen: dict[tuple[str, str], frozenset[Role] | None] = {}
    for route in _scoped_routes():
        if set(route.methods or ()) & _WRITE_METHODS:
            seen[_route_key(route)] = _allowed_roles(route)
    ungated = sorted(k for k, v in seen.items() if v is None)
    assert ungated == [], f"write routes without require_roles: {ungated}"
    unlisted = sorted(set(seen) - set(_WRITE_MATRIX))
    assert unlisted == [], f"new write route missing from the N-0086 matrix: {unlisted}"
    missing = sorted(set(_WRITE_MATRIX) - set(seen))
    assert missing == [], f"matrix routes not mounted: {missing}"
    wrong = {k: sorted(r.value for r in seen[k]) for k in seen if seen[k] != _WRITE_MATRIX[k]}
    assert wrong == {}, f"write routes with the wrong allowed set: {wrong}"


def test_no_steward_router_write_admits_viewer():
    for key, allowed in _WRITE_MATRIX.items():
        assert Role.VIEWER not in allowed, key


def test_reads_stay_sign_in_only():
    gated = {
        _route_key(r): _allowed_roles(r)
        for r in _scoped_routes()
        if "GET" in (r.methods or ()) and _allowed_roles(r) is not None
    }
    assert gated == _GATED_READS, f"reads must stay readable by every signed-in role: {gated}"


# --- behaviour through the real dependency chain ---------------------------------------------


def _mock_db():
    yield MagicMock()


@pytest.fixture
def as_role():
    role_box: dict[str, Role] = {}

    def override_user() -> dict:
        return {
            "id": f"n0086-{role_box['role'].value}",
            "role": role_box["role"],
            "email": None,
            "tenant_id": "default",
            "display_name": None,
        }

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = _mock_db
    client = TestClient(app)

    def _client(role: Role) -> TestClient:
        role_box["role"] = role
        return client

    try:
        yield _client
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


_PARAM = re.compile(r"\{[^}]+\}")
_STEWARD_ROUTES = sorted(k for k, v in _WRITE_MATRIX.items() if v == _STEWARD)
_RUNNER_ROUTES = sorted(k for k, v in _WRITE_MATRIX.items() if v == _RUNNER)


def _url(path: str) -> str:
    return _PARAM.sub("not-an-int", path)


@pytest.mark.parametrize("method,path", _STEWARD_ROUTES)
def test_viewer_and_planner_get_403_on_steward_writes(as_role, method, path):
    for role in (Role.VIEWER, Role.PLANNER):
        r = as_role(role).request(method, _url(path), json={})
        assert r.status_code == 403, (role, method, path, r.status_code, r.text)
        assert r.json()["detail"] == "Insufficient role"


@pytest.mark.parametrize("method,path", [k for k in _STEWARD_ROUTES if "{" in k[1]])
def test_steward_and_admin_pass_the_gate_on_steward_writes(as_role, method, path):
    for role in (Role.STEWARD, Role.ADMIN):
        r = as_role(role).request(method, _url(path), json={})
        # 422 = the role check passed and path validation stopped the request before any handler.
        assert r.status_code == 422, (role, method, path, r.status_code, r.text)


@pytest.mark.parametrize("method,path", _RUNNER_ROUTES)
def test_viewer_gets_403_on_job_runner_routes(as_role, method, path):
    r = as_role(Role.VIEWER).request(method, _url(path), json={})
    assert r.status_code == 403, (method, path, r.status_code, r.text)


@pytest.mark.parametrize("method,path", _RUNNER_ROUTES)
def test_planner_steward_admin_pass_the_route_gate_on_job_runner_routes(as_role, method, path):
    for role in (Role.PLANNER, Role.STEWARD, Role.ADMIN):
        # /jobs has no path parameter: the missing multipart form is the 422 instead.
        r = as_role(role).request(method, _url(path))
        assert r.status_code == 422, (role, method, path, r.status_code, r.text)


# --- per-template check behind the job-runner routes ------------------------------------------


def _user(role: Role) -> dict:
    return {"id": "u", "role": role}


@pytest.mark.parametrize("slug", sorted(PLANNER_UPLOAD_TEMPLATES))
def test_planner_may_upload_and_process_cpor_templates(slug):
    require_import_template_role(_user(Role.PLANNER), slug, PLANNER_UPLOAD_TEMPLATES)


@pytest.mark.parametrize(
    "slug", ["distributor_sales_inventory", "customer_sell_through", "inbound_shipments", "cpor_claim_evidence", "", None]
)
def test_planner_may_not_upload_steward_templates(slug):
    with pytest.raises(HTTPException) as exc:
        require_import_template_role(_user(Role.PLANNER), slug, PLANNER_UPLOAD_TEMPLATES)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("slug", sorted(PLANNER_RUN_TEMPLATES))
def test_planner_may_cancel_and_retry_lineup_and_cpor_jobs(slug):
    require_import_template_role(_user(Role.PLANNER), slug, PLANNER_RUN_TEMPLATES)


def test_lineup_templates_are_not_planner_upload_templates():
    # Lineup jobs are created by the commercial-planner routes, never by POST /imports/jobs.
    assert {"current_lineup", "unified_lineup", "bulk_lineup_backfill"}.isdisjoint(PLANNER_UPLOAD_TEMPLATES)


@pytest.mark.parametrize("role", [Role.STEWARD, Role.ADMIN])
@pytest.mark.parametrize("slug", ["distributor_sales_inventory", "cpor_payment_evidence", None])
def test_steward_and_admin_pass_every_template(role, slug):
    require_import_template_role(_user(role), slug, PLANNER_UPLOAD_TEMPLATES)


@pytest.mark.parametrize("user", [None, {}, {"role": Role.VIEWER}, {"role": "viewer"}])
def test_viewer_or_missing_user_never_passes_the_template_check(user):
    with pytest.raises(HTTPException) as exc:
        require_import_template_role(user, "cpor_payment_evidence", PLANNER_UPLOAD_TEMPLATES)
    assert exc.value.status_code == 403
