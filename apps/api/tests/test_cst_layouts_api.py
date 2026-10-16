"""N-0111 (Warren 2026-10-16): the sell-through upload endpoints take a reporting customer, not a source."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

ADMIN = {"X-User-Role": "admin"}
FILE = ("files", ("a.csv", b"SKU,Units\nA1,1\n", "text/csv"))


def test_reporting_customers_and_layouts_are_listed() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/imports/cst/reporting-customers", headers=ADMIN)
        assert r.status_code == 200
        for row in r.json():
            assert {"id", "name", "layout_count"} <= set(row)
            assert "code" not in row  # the name alone identifies a customer on screen
        assert client.get("/api/v1/imports/cst/layouts", params={"customer_id": 0}, headers=ADMIN).json() == []
        assert client.get("/api/v1/imports/cst/layouts", headers=ADMIN).status_code == 422


def test_unknown_layout_patch_is_404_and_a_blank_name_is_refused() -> None:
    with TestClient(app) as client:
        assert client.patch("/api/v1/imports/cst/layouts/0", json={"name": "x"}, headers=ADMIN).status_code == 404
        assert client.patch("/api/v1/imports/cst/layouts/0", json={"name": ""}, headers=ADMIN).status_code == 422


def test_upload_for_a_customer_that_is_not_a_reporting_customer_is_refused() -> None:
    with TestClient(app) as client:
        r = client.post("/api/v1/imports/cst/batch-jobs", data={"customer_id": "0"}, files=[FILE], headers=ADMIN)
        assert r.status_code == 400 and "reporting customer" in r.json()["detail"]
        r = client.post("/api/v1/imports/cst/batch-propose", data={"customer_id": "0"}, files=[FILE], headers=ADMIN)
        assert r.status_code == 400 and "reporting customer" in r.json()["detail"]
        # A source is no longer part of the request.
        r = client.post("/api/v1/imports/cst/batch-jobs", data={"source_id": "1"}, files=[FILE], headers=ADMIN)
        assert r.status_code == 422
