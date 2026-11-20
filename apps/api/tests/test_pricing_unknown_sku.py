"""Retired pricing endpoints cannot create facts, customers or unknown-SKU queue rows."""

import inspect
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.v1.endpoints import pricing as pricing_endpoint
from app.services import facts_upsert, pricing_unknown_sku


@pytest.fixture
def pricing_client(monkeypatch):
    async def refuse_database():
        pytest.fail("A retired pricing write requested a database session")
        yield

    resolve_customer = AsyncMock(
        side_effect=AssertionError("Retired pricing reached customer resolution")
    )
    queue_sku = AsyncMock(
        side_effect=AssertionError("Retired pricing reached the unknown-SKU queue")
    )
    clear_sku = AsyncMock(
        side_effect=AssertionError("Retired pricing changed the unknown-SKU queue")
    )
    monkeypatch.setattr(facts_upsert, "resolve_customer_id", resolve_customer)
    monkeypatch.setattr(pricing_unknown_sku, "queue_unknown_pricing_sku", queue_sku)
    monkeypatch.setattr(pricing_unknown_sku, "clear_queued_pricing_sku", clear_sku)

    application = FastAPI()
    application.include_router(pricing_endpoint.router, prefix="/pricing")
    application.dependency_overrides[get_db] = refuse_database

    with TestClient(application) as client:
        yield client

    resolve_customer.assert_not_called()
    queue_sku.assert_not_called()
    clear_sku.assert_not_called()


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/pricing/facts"),
        ("POST", "/pricing/facts/bulk"),
        ("POST", "/pricing/facts/clear-all"),
        ("DELETE", "/pricing/facts/123"),
        ("DELETE", "/pricing/recommendations/123"),
        ("POST", "/pricing/recommendations/clear-all"),
        ("PUT", "/pricing/facts/123"),
        ("PATCH", "/pricing/facts/123"),
        ("DELETE", "/pricing"),
    ],
)
def test_pricing_writes_are_gone_before_body_validation_or_database_access(
    pricing_client, method, path
):
    response = pricing_client.request(
        method,
        path,
        content=b"not valid JSON",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 410
    assert response.json()["detail"]["message"] == pricing_endpoint.RETIRED_PRICING_MESSAGE


def test_retired_pricing_read_returns_the_replacement_routes(pricing_client):
    response = pricing_client.get("/pricing/recommendations")

    assert response.status_code == 200
    assert response.json() == {
        "message": pricing_endpoint.RETIRED_PRICING_MESSAGE,
        "lineup_href": "/lineup",
        "listings_href": "/listing-capture?tab=registry",
    }


def test_pricing_module_has_no_customer_or_queue_write_path():
    source = inspect.getsource(pricing_endpoint)

    assert "resolve_customer_id" not in source
    assert "queue_unknown_pricing_sku" not in source
    assert "clear_queued_pricing_sku" not in source
    assert ".commit(" not in source
    assert ".delete(" not in source
    assert ".add(" not in source
