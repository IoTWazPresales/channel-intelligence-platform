from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app


def _fake_product(**overrides):
    base = {
        "id": 1,
        "sku": "SKU-001",
        "part_number": "PN-001",
        "name": "Widget",
        "sales_model_name": "Widget Sales",
        "model_name": "Widget Model",
        "series_name": "Widget Series",
        "product_line": "Widget Line",
        "business_unit": "Consumer",
        "category": "Audio",
        "form_factor": "Bar",
        "country_code": "ZA",
        "ean": "1234567890123",
        "upc": "123456789012",
        "lifecycle_status": "active",
        "launch_date": date(2024, 1, 1),
        "retired_date": None,
        "is_active": True,
        "channel_id": 10,
        "specs_json": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_products_list_response_shape_and_pagination_contract():
    sess = MagicMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 2
    rows_res = MagicMock()
    rows_res.all.return_value = [
        (_fake_product(id=1, sku="A-SKU", specs_json={"RAM": "16GB", "CPU": "X1"}), "RET", date(2026, 1, 10)),
        (_fake_product(id=2, sku="B-SKU", category=None, channel_id=None), None, None),
    ]
    sess.execute = AsyncMock(side_effect=[count_res, rows_res])

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            r = client.get(
                "/api/v1/products",
                params={"page": 1, "page_size": 25, "sort_by": "sku", "sort_dir": "asc", "q": "SKU"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["page"] == 1
        assert body["page_size"] == 25
        assert body["total"] == 2
        assert body["sort_by"] == "sku"
        assert body["sort_dir"] == "asc"
        assert len(body["items"]) == 2
        assert body["items"][0]["sku"] == "A-SKU"
        assert body["items"][0]["part_number"] == "PN-001"
        assert body["items"][0]["sales_model_name"] == "Widget Sales"
        assert body["items"][0]["model_name"] == "Widget Model"
        assert body["items"][0]["series_name"] == "Widget Series"
        assert body["items"][0]["product_line"] == "Widget Line"
        assert body["items"][0]["business_unit"] == "Consumer"
        assert body["items"][0]["country_code"] == "ZA"
        assert body["items"][0]["ean"] == "1234567890123"
        assert body["items"][0]["upc"] == "123456789012"
        assert body["items"][0]["missing_required_fields"] == []
        assert body["items"][0]["last_import_date"] == "2026-01-10"
        assert body["items"][0]["specs_preview"] == {"CPU": "X1", "RAM": "16GB"}
        assert body["items"][1]["specs_preview"] == {}
        assert "category" in body["items"][1]["missing_required_fields"]
        assert "channel" in body["items"][1]["missing_required_fields"]
    finally:
        app.dependency_overrides.clear()


def test_products_list_unknown_sort_falls_back_to_sku():
    sess = MagicMock()
    count_res = MagicMock()
    count_res.scalar_one.return_value = 0
    rows_res = MagicMock()
    rows_res.all.return_value = []
    sess.execute = AsyncMock(side_effect=[count_res, rows_res])

    async def fake_db():
        yield sess

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/products", params={"sort_by": "not_a_field", "sort_dir": "desc"})
        assert r.status_code == 200
        body = r.json()
        assert body["sort_by"] == "sku"
        assert body["sort_dir"] == "desc"
        assert body["items"] == []
    finally:
        app.dependency_overrides.clear()
