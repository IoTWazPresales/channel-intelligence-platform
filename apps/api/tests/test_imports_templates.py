"""Import template + filtered sources API."""

from fastapi.testclient import TestClient

from app.db.session_sync import SessionLocal
from app.main import app
from app.services.seed_demo import _seed_import_core
from app.services.imports.template_definitions import product_master_sample_csv


def test_product_master_sample_csv_content() -> None:
    assert "sku,name" in product_master_sample_csv()


def test_imports_templates_and_sources() -> None:
    with SessionLocal() as seed_db:
        _seed_import_core(seed_db)
        seed_db.commit()

    with TestClient(app) as client:
        r = client.get("/api/v1/imports/templates", headers={"X-User-Role": "admin"})
        assert r.status_code == 200
        slugs = {t["slug"] for t in r.json()}
        assert "product_master" in slugs
        assert "distributor_master" in slugs
        assert "distributor_inventory" in slugs
        assert "customer_master" in slugs
        assert "customer_channel_mapping" in slugs
        assert "historical_lineup" in slugs

        by_slug = {t["slug"]: t for t in r.json()}
        assert by_slug["distributor_master"]["pipeline_handler"] == "distributor_master_upsert"
        assert by_slug["distributor_master"]["pipeline_ready"] is True
        assert by_slug["customer_master"]["pipeline_handler"] == "customer_master_upsert"
        assert by_slug["customer_master"]["pipeline_ready"] is True
        assert by_slug["customer_channel_mapping"]["pipeline_handler"] == "stub_noop"
        assert by_slug["customer_channel_mapping"]["pipeline_ready"] is False
        assert by_slug["historical_lineup"]["pipeline_handler"] == "historical_lineup_workbook"
        assert by_slug["historical_lineup"]["pipeline_ready"] is True
        assert by_slug["distributor_inventory"]["pipeline_handler"] == "distributor_sales_inventory"
        assert by_slug["distributor_inventory"]["pipeline_ready"] is True

        r2 = client.get(
            "/api/v1/imports/sources",
            params={"template_slug": "product_master"},
            headers={"X-User-Role": "admin"},
        )
        assert r2.status_code == 200
        rows = r2.json()
        assert all(x.get("import_template_slug") == "product_master" for x in rows)

        r_customer = client.get(
            "/api/v1/imports/sources",
            params={"template_slug": "customer_master"},
            headers={"X-User-Role": "admin"},
        )
        assert r_customer.status_code == 200
        customer_sources = r_customer.json()
        assert customer_sources
        assert all(x.get("import_template_slug") == "customer_master" for x in customer_sources)

        r_distributor = client.get(
            "/api/v1/imports/sources",
            params={"template_slug": "distributor_master"},
            headers={"X-User-Role": "admin"},
        )
        assert r_distributor.status_code == 200
        distributor_sources = r_distributor.json()
        assert distributor_sources
        assert all(x.get("import_template_slug") == "distributor_master" for x in distributor_sources)

    with TestClient(app) as client2:
        r3 = client2.get("/api/v1/imports/templates/product_master/sample")
        assert r3.status_code == 200
        assert "sku,name" in r3.text
