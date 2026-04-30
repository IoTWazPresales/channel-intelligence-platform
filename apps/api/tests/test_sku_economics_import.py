"""Unit and API contract tests for SKU economics CSV import."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.commercial_planner.sku_economics_import import (
    TEMPLATE_HEADERS,
    build_product_index,
    build_template_csv,
    decode_csv_rows,
    preview_sku_economics_import,
    resolve_product_id,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_build_template_csv_has_headers_and_example_row():
    csv_text = build_template_csv()
    lines = csv_text.strip().splitlines()
    assert len(lines) >= 2
    assert lines[0].split(",")[0] == TEMPLATE_HEADERS[0]


def test_decode_rejects_dap_style_column():
    raw = "sku,dap_local,controlled_cost_amount\nX,1,10\n"
    rows, errs = decode_csv_rows(raw.encode())
    assert rows == []
    assert errs and any("not allowed" in e for e in errs)


def test_decode_allows_notes_column_ignored():
    headers = ",".join(
        [
            "sku",
            "part_number",
            "sales_model",
            "model_name",
            "controlled_cost_amount",
            "controlled_cost_currency_code",
            "fx_plan_currency_per_cost_currency",
            "vat_rate_pct",
            "reserve_total_pct",
            "campaign_support_reserve_split_pct",
            "notes",
        ]
    )
    raw = headers + "\nSKU1,,,10,USD,1,0.15,0.1,0.5,hello\n"
    rows, errs = decode_csv_rows(raw.encode())
    assert not errs
    assert len(rows) == 1
    assert "notes" not in rows[0]


def test_resolve_prefers_sku_over_part_number():
    p1 = SimpleNamespace(id=1, sku="A", part_number="PN1", sales_model_name="S", model_name="M")
    idx = build_product_index([p1])
    pid, method, err = resolve_product_id(
        {"sku": "A", "part_number": "WRONG", "sales_model": "", "model_name": ""},
        idx,
    )
    assert err is None
    assert method == "sku"
    assert pid == 1


def test_resolve_unique_sales_model_pair():
    p1 = SimpleNamespace(id=2, sku="", part_number="", sales_model_name="SM1", model_name="MN1")
    idx = build_product_index([p1])
    pid, method, err = resolve_product_id(
        {"sku": "", "part_number": "", "sales_model": "SM1", "model_name": "MN1"},
        idx,
    )
    assert err is None
    assert method == "sales_model_model_name"
    assert pid == 2


def test_get_import_template_contract():
    r = client.get("/api/v1/commercial-planner/sku-assumptions/import-template")
    assert r.status_code == 200
    assert "sku" in r.text.splitlines()[0]


def test_patch_plan_currency_persisted_in_response():
    from datetime import date

    plan = SimpleNamespace(
        id=1,
        plan_name="P",
        status="draft",
        period_start=date(2026, 1, 1),
        period_end=None,
        owner=None,
        environment=None,
        country_code="ZA",
        currency_code="USD",
        notes=None,
    )

    async def fake_db():
        sess = MagicMock()
        sess.get = AsyncMock(return_value=plan)
        lc = MagicMock()
        lc.scalar_one = MagicMock(return_value=3)
        sess.execute = AsyncMock(return_value=lc)
        sess.commit = AsyncMock()
        sess.refresh = AsyncMock()
        yield sess

    app.dependency_overrides[get_db] = fake_db
    r = client.patch("/api/v1/commercial-planner/plans/1", json={"currency_code": "ZAR"})
    assert r.status_code == 200
    body = r.json()
    assert body["currency_code"] == "ZAR"
    assert body["line_count"] == 3
    assert plan.currency_code == "ZAR"


def test_preview_sku_economics_import_async_unit():
    product = SimpleNamespace(
        id=99,
        sku="SKU-IM",
        part_number="PN-IM",
        sales_model_name="SM",
        model_name="MN",
        name="Widget",
    )

    class FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return FakeScalars(self._items)

    class FakeSession:
        def __init__(self):
            self._calls = 0

        async def execute(self, _stmt):
            self._calls += 1
            if self._calls == 1:
                return FakeResult([product])
            return FakeResult([])

    async def _run_empty():
        out = await preview_sku_economics_import(FakeSession(), b"")
        assert out["parse_errors"] == ["File is empty"]

    asyncio.run(_run_empty())

    async def _run_preview():
        csv_body = (
            "sku,part_number,sales_model,model_name,controlled_cost_amount,controlled_cost_currency_code,"
            "fx_plan_currency_per_cost_currency,vat_rate_pct,reserve_total_pct,campaign_support_reserve_split_pct\n"
            "SKU-IM,,,,100,USD,18.5,15,10,50\n"
        )
        out = await preview_sku_economics_import(FakeSession(), csv_body.encode())
        assert out["can_apply"] is True
        assert out["summary"]["creates"] == 1
        row = out["rows"][0]
        assert row["action"] == "create"
        assert row["match_method"] == "sku"
        assert row["proposed"]["vat_rate_pct"] == pytest.approx(0.15)

    asyncio.run(_run_preview())
