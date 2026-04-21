"""Import template + filtered sources API."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.imports.template_definitions import product_master_sample_csv


def test_product_master_sample_csv_content() -> None:
    assert "sku,name" in product_master_sample_csv()


def test_imports_templates_and_sources() -> None:
    with TestClient(app) as client:
        r = client.get("/api/v1/imports/templates", headers={"X-User-Role": "admin"})
        assert r.status_code == 200
        slugs = {t["slug"] for t in r.json()}
        assert "product_master" in slugs
        assert "distributor_inventory" in slugs

        r2 = client.get(
            "/api/v1/imports/sources",
            params={"template_slug": "product_master"},
            headers={"X-User-Role": "admin"},
        )
        assert r2.status_code == 200
        rows = r2.json()
        assert all(x.get("import_template_slug") == "product_master" for x in rows)

    with TestClient(app) as client2:
        r3 = client2.get("/api/v1/imports/templates/product_master/sample")
        assert r3.status_code == 200
        assert "sku,name" in r3.text
