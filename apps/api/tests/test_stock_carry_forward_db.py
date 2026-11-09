"""DB tests for D-0119 distributor stock carry-forward (cip_test only; rolled back)."""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.models.dimensions import DimDistributor, DimProduct
from app.models.facts import FactInventoryDistributor
from app.query.cache import clear_query_cache
from app.query.model.execute import run_v2
from app.query.model.graph import V2Request
from app.query.model.loader import clear_model_cache

TAG = secrets.token_hex(3)
TENANT = f"d0119-{TAG}"


@pytest.fixture(autouse=True)
def _clear():
    clear_query_cache()
    clear_model_cache()
    yield
    clear_query_cache()
    clear_model_cache()


async def _session_or_skip():
    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    if name != "cip_test":
        await db.close()
        pytest.skip("cip_test only")
    return db


async def _seed(db):
    dist = DimDistributor(tenant_id=TENANT, code=f"DCF{TAG}"[-32:], name=f"Carry Dist {TAG}")
    p1 = DimProduct(tenant_id=TENANT, sku=f"CF1-{TAG}", name=f"Carry SKU 1 {TAG}")
    p2 = DimProduct(tenant_id=TENANT, sku=f"CF2-{TAG}", name=f"Carry SKU 2 {TAG}")
    ghost = DimProduct(tenant_id=TENANT, sku=f"CFG-{TAG}", name=f"Ghost {TAG}")
    db.add_all([dist, p1, p2, ghost])
    await db.flush()
    db.add_all(
        [
            FactInventoryDistributor(
                source_key=f"cf-{TAG}-{dist.id}-{p1.id}-jan",
                tenant_id=TENANT,
                product_id=p1.id,
                distributor_id=dist.id,
                as_of_date=date(2026, 1, 15),
                on_hand_units=40,
            ),
            FactInventoryDistributor(
                source_key=f"cf-{TAG}-{dist.id}-{p1.id}-mar",
                tenant_id=TENANT,
                product_id=p1.id,
                distributor_id=dist.id,
                as_of_date=date(2026, 3, 10),
                on_hand_units=25,
            ),
            FactInventoryDistributor(
                source_key=f"cf-{TAG}-{dist.id}-{p2.id}-jan",
                tenant_id=TENANT,
                product_id=p2.id,
                distributor_id=dist.id,
                as_of_date=date(2026, 1, 15),
                on_hand_units=10,
            ),
        ]
    )
    await db.flush()
    return dist, p1, p2, ghost


@pytest.mark.anyio
async def test_current_database_is_cip_test():
    db = await _session_or_skip()
    try:
        name = (await db.execute(text("select current_database()"))).scalar_one()
        assert name == "cip_test"
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_period_without_count_carries_forward_and_is_flagged():
    db = await _session_or_skip()
    try:
        dist, p1, _, _ = await _seed(db)
        resp = await run_v2(
            db,
            V2Request(
                measures=["distributor_stock.on_hand"],
                breakdowns=["period", "distributor", "product"],
                period_grain="month",
                period_from="2026-01-01",
                period_to="2026-03-31",
                filters={"distributor": [dist.id], "product": [p1.id]},
            ),
            tenant_id=TENANT,
            skip_cache=True,
        )
        assert resp["ok"], resp.get("refusals")
        by = {r["bucket_start"]: r for r in resp["rows"]}
        assert by["2026-01-01"]["distributor_stock.on_hand"] == 40.0
        assert by["2026-01-01"]["distributor_stock.on_hand_carried_forward"] == 0.0
        assert by["2026-02-01"]["distributor_stock.on_hand"] == 40.0
        assert by["2026-02-01"]["distributor_stock.on_hand_carried_forward"] == 1.0
        assert by["2026-03-01"]["distributor_stock.on_hand"] == 25.0
        assert by["2026-03-01"]["distributor_stock.on_hand_carried_forward"] == 0.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_new_count_replaces_carried_value_in_later_bucket():
    db = await _session_or_skip()
    try:
        dist, p1, _, _ = await _seed(db)
        resp = await run_v2(
            db,
            V2Request(
                measures=["distributor_stock.on_hand"],
                breakdowns=["period", "product"],
                period_grain="month",
                period_from="2026-02-01",
                period_to="2026-03-31",
                filters={"distributor": [dist.id], "product": [p1.id]},
            ),
            tenant_id=TENANT,
            skip_cache=True,
        )
        assert resp["ok"], resp.get("refusals")
        by = {r["bucket_start"]: r for r in resp["rows"]}
        assert by["2026-02-01"]["distributor_stock.on_hand"] == 40.0
        assert by["2026-02-01"]["distributor_stock.on_hand_carried_forward"] == 1.0
        assert by["2026-03-01"]["distributor_stock.on_hand"] == 25.0
        assert by["2026-03-01"]["distributor_stock.on_hand_carried_forward"] == 0.0
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_never_counted_product_stays_empty():
    db = await _session_or_skip()
    try:
        dist, _, _, ghost = await _seed(db)
        resp = await run_v2(
            db,
            V2Request(
                measures=["distributor_stock.on_hand"],
                breakdowns=["period", "product"],
                period_grain="month",
                period_from="2026-01-01",
                period_to="2026-02-28",
                filters={"distributor": [dist.id], "product": [ghost.id]},
            ),
            tenant_id=TENANT,
            skip_cache=True,
        )
        assert resp["ok"], resp.get("refusals")
        assert resp["rows"] == []
        assert resp["totals"]["distributor_stock.on_hand"] is None
    finally:
        await db.rollback()
        await db.close()

@pytest.mark.anyio
async def test_unbounded_period_derives_spine_from_data():
    """Catalog offers period grains without from/to; execute derives the spine from first/last count."""
    db = await _session_or_skip()
    try:
        dist, p1, _, _ = await _seed(db)
        name = (await db.execute(text("select current_database()"))).scalar_one()
        assert name == "cip_test"
        resp = await run_v2(
            db,
            V2Request(
                measures=["distributor_stock.on_hand"],
                breakdowns=["period", "product"],
                period_grain="month",
                filters={"distributor": [dist.id], "product": [p1.id]},
            ),
            tenant_id=TENANT,
            skip_cache=True,
        )
        assert resp["ok"], resp.get("refusals")
        by = {r["bucket_start"]: r for r in resp["rows"]}
        # Seed has Jan 15 (40) and Mar 10 (25); Feb gap carries Jan.
        assert set(by) == {"2026-01-01", "2026-02-01", "2026-03-01"}
        assert by["2026-01-01"]["distributor_stock.on_hand"] == 40.0
        assert by["2026-01-01"]["distributor_stock.on_hand_carried_forward"] == 0.0
        assert by["2026-02-01"]["distributor_stock.on_hand"] == 40.0
        assert by["2026-02-01"]["distributor_stock.on_hand_carried_forward"] == 1.0
        assert by["2026-03-01"]["distributor_stock.on_hand"] == 25.0
        assert by["2026-03-01"]["distributor_stock.on_hand_carried_forward"] == 0.0
        notes = (resp.get("explain") or {}).get("notes") or []
        assert any("derived from data counts" in n for n in notes), notes
    finally:
        await db.rollback()
        await db.close()

