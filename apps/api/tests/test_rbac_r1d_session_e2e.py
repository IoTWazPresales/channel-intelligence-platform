"""RBAC R1d — first evidence a human can use the app after R1–R1c.

Requires process env (do not write .env):
  CIP_AUTH_MODE=session
  DATABASE_URL and DATABASE_URL_SYNC pointing at cip_test (both names printed).
Refuses to run if either URL names `cip`. Seeds only cip_test.
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.password import hash_password
from app.db.migrate_url_guard import database_name_from_url, redact_database_url
from app.db.session_sync import SessionLocal
from app.main import app
from app.models.dimensions import DimProduct
from app.models.iam import AppUser, Tenant
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.seed_demo import _seed_import_core

_ADMIN_EMAIL = "r1d.admin@local"
_VIEWER_EMAIL = "r1d.viewer@local"
_ADMIN_PASSWORD = "r1d-admin-pass"
_VIEWER_PASSWORD = "r1d-viewer-pass"
_PRODUCT_SKU = "R1D-E2E-SKU"
_DSI_JOB_FILE = "r1d-e2e-dsi.xlsx"
_PM_JOB_FILE = "r1d-e2e-pm.xlsx"


def _print_and_assert_cip_test() -> None:
    settings = get_settings()
    async_url = settings.database_url
    sync_url = settings.database_url_sync
    migrate_url = settings.database_url_sync_migrate or ""
    async_name = database_name_from_url(async_url)
    sync_name = database_name_from_url(sync_url)
    migrate_name = database_name_from_url(migrate_url) if migrate_url else None
    auth_mode = (settings.cip_auth_mode or "").strip().lower()
    print(f"DATABASE_URL={redact_database_url(async_url)} dbname={async_name!r}")
    print(f"DATABASE_URL_SYNC={redact_database_url(sync_url)} dbname={sync_name!r}")
    print(
        f"DATABASE_URL_SYNC_MIGRATE={redact_database_url(migrate_url) if migrate_url else None} "
        f"dbname={migrate_name!r}"
    )
    print(f"CIP_AUTH_MODE={auth_mode!r} (process={os.environ.get('CIP_AUTH_MODE')!r})")
    assert async_name == "cip_test", f"DATABASE_URL must name cip_test, got {async_name!r}"
    assert sync_name == "cip_test", f"DATABASE_URL_SYNC must name cip_test, got {sync_name!r}"
    assert auth_mode == "session", f"CIP_AUTH_MODE must be session, got {auth_mode!r}"


def _upsert_user(session, *, email: str, role: str, password: str, display_name: str) -> None:
    if session.get(Tenant, "default") is None:
        session.add(Tenant(id="default", name="Default"))
        session.flush()
    row = session.scalar(
        select(AppUser).where(AppUser.tenant_id == "default", AppUser.email == email)
    )
    if row is None:
        session.add(
            AppUser(
                tenant_id="default",
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
                role=role,
                is_active=True,
            )
        )
        return
    row.role = role
    row.is_active = True
    row.password_hash = hash_password(password)
    row.display_name = display_name


def _seed_fixtures() -> tuple[int, int, int]:
    with SessionLocal() as session:
        connected = session.get_bind().url.database
        assert connected == "cip_test", f"SessionLocal connected {connected!r}"
        _upsert_user(
            session,
            email=_ADMIN_EMAIL,
            role="admin",
            password=_ADMIN_PASSWORD,
            display_name="R1d Admin",
        )
        _upsert_user(
            session,
            email=_VIEWER_EMAIL,
            role="viewer",
            password=_VIEWER_PASSWORD,
            display_name="R1d Viewer",
        )
        _seed_import_core(session)
        product = session.scalar(select(DimProduct).where(DimProduct.sku == _PRODUCT_SKU))
        if product is None:
            product = DimProduct(sku=_PRODUCT_SKU, name="R1d e2e product")
            session.add(product)
            session.flush()
        dsi_src = session.scalar(
            select(SourceDefinition).where(SourceDefinition.code == "distributor_inventory")
        )
        assert dsi_src is not None, "distributor_inventory source missing after _seed_import_core"
        dsi_job = session.scalar(select(ImportJob).where(ImportJob.file_name == _DSI_JOB_FILE))
        if dsi_job is None:
            dsi_job = ImportJob(
                source_id=dsi_src.id,
                template_slug="distributor_inventory",
                status="pending",
                stage="uploaded",
                file_name=_DSI_JOB_FILE,
            )
            session.add(dsi_job)
            session.flush()
        pm_src = session.scalar(
            select(SourceDefinition).where(SourceDefinition.code == "product_catalog_default")
        )
        assert pm_src is not None, "product_catalog_default source missing after _seed_import_core"
        pm_job = session.scalar(select(ImportJob).where(ImportJob.file_name == _PM_JOB_FILE))
        if pm_job is None:
            pm_job = ImportJob(
                source_id=pm_src.id,
                template_slug="product_master",
                status="pending",
                stage="uploaded",
                file_name=_PM_JOB_FILE,
            )
            session.add(pm_job)
            session.flush()
        session.commit()
        return int(product.id), int(dsi_job.id), int(pm_job.id)


def _login(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    token = res.json().get("token")
    assert isinstance(token, str) and token, res.text
    return token


def _call(client: TestClient, method: str, path: str, *, token: str | None, json: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    kwargs: dict = {}
    if json is not None:
        kwargs["json"] = json
    return client.request(method, path, headers=headers, **kwargs)


# One swept require_roles(ADMIN) route per R1c router.
def _swept_calls(product_id: int, dsi_job_id: int, pm_job_id: int) -> list[tuple[str, str, str, dict | None]]:
    return [
        ("shipment_evidence", "GET", "/api/v1/shipment-evidence?limit=1", None),
        (
            "mappings",
            "POST",
            f"/api/v1/mappings/import-jobs/{dsi_job_id}/dsi-geo-steward/bulk-apply",
            {
                "action": "register_region_from_hint",
                "items": [{"kind": "channel", "raw_token": "r1d-nonexistent-geo-token"}],
            },
        ),
        (
            "imports_product_master",
            "GET",
            f"/api/v1/imports/product-master/jobs/{pm_job_id}/state",
            None,
        ),
        (
            "products",
            "GET",
            f"/api/v1/products/id/{product_id}/dependencies/distributor-inventory",
            None,
        ),
        (
            "imports",
            "POST",
            "/api/v1/imports/jobs/bulk-delete-preview",
            {"job_ids": [1]},
        ),
    ]


def test_r1d_session_login_admin_200_viewer_403_anon_401() -> None:
    _print_and_assert_cip_test()
    product_id, dsi_job_id, pm_job_id = _seed_fixtures()
    routes = _swept_calls(product_id, dsi_job_id, pm_job_id)
    with TestClient(app) as client:
        admin_token = _login(client, _ADMIN_EMAIL, _ADMIN_PASSWORD)
        viewer_token = _login(client, _VIEWER_EMAIL, _VIEWER_PASSWORD)
        for router_name, method, path, body in routes:
            anon = _call(client, method, path, token=None, json=body)
            assert anon.status_code == 401, f"{router_name} anon expected 401 got {anon.status_code}: {anon.text}"
            viewer = _call(client, method, path, token=viewer_token, json=body)
            assert viewer.status_code == 403, (
                f"{router_name} viewer expected 403 got {viewer.status_code}: {viewer.text}"
            )
            admin = _call(client, method, path, token=admin_token, json=body)
            assert admin.status_code == 200, (
                f"{router_name} admin expected 200 got {admin.status_code}: {admin.text}"
            )
            print(f"PASS {router_name} {method} {path} admin=200 viewer=403 anon=401")
