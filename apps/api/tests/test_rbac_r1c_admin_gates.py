"""RBAC R1c — non-CPOR admin header gates replaced with require_roles(Role.ADMIN).

No database writes: FastAPI route introspection only.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.core.security import get_current_user
from app.main import app

_REQUIRE_ROLES_DEP_QUALNAME = "require_roles.<locals>._dep"

# Exact routes that previously called a local _require_admin / _require_admin_role /
# _require_admin_import_maintenance helper. Do not widen this set.
_SWEPT_REQUIRE_ADMIN: frozenset[tuple[str, str]] = frozenset(
    {
        # shipment_evidence.py — 25
        ("GET", "/api/v1/shipment-evidence/raw-column-keys"),
        ("GET", "/api/v1/shipment-evidence/import-jobs/{job_id}/mapping-candidates"),
        ("GET", "/api/v1/shipment-evidence/import-jobs/{job_id}/mapping-candidates/paginated"),
        ("GET", "/api/v1/shipment-evidence/import-jobs/{job_id}/mapping-candidates/tab-counts"),
        ("POST", "/api/v1/shipment-evidence/import-jobs/{job_id}/resolution-plan/compute-async"),
        ("POST", "/api/v1/shipment-evidence/import-jobs/{job_id}/resolution-plan"),
        ("POST", "/api/v1/shipment-evidence/import-jobs/{job_id}/resolution-plan/effective"),
        ("POST", "/api/v1/shipment-evidence/import-jobs/{job_id}/resolution-plan/apply-async"),
        ("POST", "/api/v1/shipment-evidence/import-jobs/{job_id}/bulk-apply-confirmed-plans"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/bulk-map-customer"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/map-distributor"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/create-provisional-distributor"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/map-customer"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/manual-special-category"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/clear-special-category"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/reject"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/duplicate-review/different-entity"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/duplicate-review/same-entity"),
        ("POST", "/api/v1/shipment-evidence/import-candidates/{candidate_id}/create-provisional-customer"),
        ("POST", "/api/v1/shipment-evidence/import-jobs/{job_id}/bulk-create-provisional-customers"),
        (
            "POST",
            "/api/v1/shipment-evidence/import-jobs/{job_id}/shipment-steward-bulk-provisional-customers/apply-async",
        ),
        ("POST", "/api/v1/shipment-evidence/jobs/{job_id}/apply"),
        ("GET", "/api/v1/shipment-evidence"),
        ("GET", "/api/v1/shipment-evidence/change-events"),
        ("GET", "/api/v1/shipment-evidence/{line_id}"),
        # mappings.py — 7
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-apply-complete"),
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-geo-steward/channel-create"),
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-geo-steward/channel-alias"),
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-geo-steward/region-create"),
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-geo-steward/region-alias"),
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-geo-steward/region-register-from-hint"),
        ("POST", "/api/v1/mappings/import-jobs/{job_id}/dsi-geo-steward/bulk-apply"),
        # imports_product_master.py — 5
        ("POST", "/api/v1/imports/product-master/jobs"),
        ("GET", "/api/v1/imports/product-master/jobs/{job_id}/state"),
        ("PUT", "/api/v1/imports/product-master/jobs/{job_id}/mapping"),
        ("POST", "/api/v1/imports/product-master/jobs/{job_id}/validate"),
        ("POST", "/api/v1/imports/product-master/jobs/{job_id}/commit"),
        # products.py — 2
        ("GET", "/api/v1/products/id/{product_id}/dependencies/distributor-inventory"),
        ("DELETE", "/api/v1/products/id/{product_id}/dependencies/distributor-inventory"),
        # imports.py — 2 gates (filter GETs are authenticated, not require_roles)
        ("POST", "/api/v1/imports/jobs/bulk-delete-preview"),
        ("POST", "/api/v1/imports/jobs/bulk-delete-confirm"),
    }
)

_FILTER_AUTH_ONLY: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/v1/imports/templates"),
        ("GET", "/api/v1/imports/templates/{slug}"),
        ("GET", "/api/v1/imports/sources"),
    }
)


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


def _has_require_roles(dependant) -> bool:
    return any(getattr(call, "__qualname__", "") == _REQUIRE_ROLES_DEP_QUALNAME for call in _dependant_calls(dependant))


def _route_key(route: APIRoute) -> tuple[str, str]:
    methods = sorted(m for m in (route.methods or ()) if m not in {"HEAD", "OPTIONS"})
    method = methods[0] if methods else ""
    return (method, route.path)


def test_swept_admin_routes_depend_on_require_roles():
    mounted: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        key = _route_key(route)
        if key in _SWEPT_REQUIRE_ADMIN:
            mounted[key] = route

    missing_mount = sorted(_SWEPT_REQUIRE_ADMIN - set(mounted))
    assert missing_mount == [], f"swept routes not mounted: {missing_mount}"

    missing_dep: list[tuple[str, str]] = []
    missing_user: list[tuple[str, str]] = []
    for key, route in mounted.items():
        if not _has_require_roles(route.dependant):
            missing_dep.append(key)
        if get_current_user not in _dependant_calls(route.dependant):
            missing_user.append(key)
    assert missing_dep == [], f"swept routes missing require_roles: {missing_dep}"
    assert missing_user == [], f"swept routes missing get_current_user: {missing_user}"
    assert len(mounted) == 41


def test_import_template_filters_authenticate_without_require_roles():
    mounted: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        key = _route_key(route)
        if key in _FILTER_AUTH_ONLY:
            mounted[key] = route
    missing_mount = sorted(_FILTER_AUTH_ONLY - set(mounted))
    assert missing_mount == [], f"filter routes not mounted: {missing_mount}"
    for key, route in mounted.items():
        assert get_current_user in _dependant_calls(route.dependant), key
        assert not _has_require_roles(route.dependant), f"filter route must not use require_roles: {key}"
