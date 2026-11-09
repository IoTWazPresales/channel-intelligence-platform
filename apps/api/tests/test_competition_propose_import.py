"""BACKLOG-221: propose mappings + price import against existing competition scorer."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.session import engine
from app.main import app
from app.models.dimensions import DimCompetitorBrand, DimCompetitorProduct, DimProduct
from app.services.competition.matching import (
    CompetitorCandidate,
    InternalProductProfile,
    score_competitor_candidate,
)
from app.services.competition.propose import _candidate_profile, _internal_profile, _spec_tokens


def test_score_competitor_candidate_prefers_matching_title_and_category():
    internal = InternalProductProfile(
        title="Acme Notebook 14 Pro",
        category="notebook",
        form_factor="clamshell",
        spec_tokens=["14", "intel", "16gb"],
        internal_price=1200.0,
    )
    good = CompetitorCandidate(
        title="Acme Notebook 14 Pro Rival",
        category="notebook",
        form_factor="clamshell",
        spec_tokens=["14", "intel", "16gb"],
        competitor_price=1180.0,
    )
    bad = CompetitorCandidate(
        title="Office Chair Mesh",
        category="furniture",
        form_factor="seat",
        spec_tokens=["mesh"],
        competitor_price=199.0,
    )
    good_score = score_competitor_candidate(internal, good).score
    bad_score = score_competitor_candidate(internal, bad).score
    assert good_score > bad_score
    assert good_score >= 0.55


def test_spec_tokens_flatten_lists_and_scalars():
    tokens = _spec_tokens({"ram": ["16gb", "ddr5"], "cpu": "intel"})
    assert "ram" in tokens and "16gb" in tokens and "intel" in tokens
    assert _spec_tokens(None) == []


def test_profile_helpers_read_name_sku_and_form_factor():
    class P:
        name = "Internal One"
        sku = "INT-1"
        category = "notebook"
        form_factor = "clamshell"
        specs_json = {"ram": "16gb"}

    class C:
        name = "Comp One"
        sku = "CMP-1"
        category = "notebook"
        specs_json = {"form_factor": "clamshell", "ram": "16gb"}

    ip = _internal_profile(P())
    assert ip.title == "Internal One" and ip.form_factor == "clamshell"
    cp = _candidate_profile(C())
    assert cp.title == "Comp One" and cp.form_factor == "clamshell"


@pytest.mark.anyio
async def test_propose_and_price_import_endpoints_on_cip_test():
    """Seed brand/competitor/product, propose pending mappings, import a price; roll back."""
    tag = secrets.token_hex(5)
    async with engine.connect() as conn:
        outer = await conn.begin()
        if (await conn.execute(text("select current_database()"))).scalar_one() != "cip_test":
            await outer.rollback()
            pytest.skip("cip_test only")
        seed = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        previous = app.dependency_overrides.get(get_db)

        async def db_for_request():
            async with AsyncSession(
                bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                yield session

        app.dependency_overrides[get_db] = db_for_request
        try:
            brand = DimCompetitorBrand(name=f"Brand-{tag}")
            seed.add(brand)
            await seed.flush()
            product = DimProduct(
                tenant_id="default",
                sku=f"INT-{tag}",
                name=f"Internal Notebook {tag}",
                category="notebook",
                form_factor="clamshell",
                specs_json={"ram": "16gb"},
            )
            comp = DimCompetitorProduct(
                brand_id=brand.id,
                sku=f"CMP-{tag}",
                name=f"Internal Notebook {tag} Rival",
                category="notebook",
                specs_json={"form_factor": "clamshell", "ram": "16gb"},
            )
            seed.add_all([product, comp])
            await seed.commit()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.post("/api/v1/competition/prices/import", json={"rows": []})
                assert r.status_code == 400, r.text

                r = await client.post(
                    "/api/v1/competition/prices/import",
                    json={"rows": [{"competitor_sku": f"NOPE-{tag}", "price": 10.0}]},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["created"] == 0 and f"NOPE-{tag}" in body["skipped_unknown_skus"]

                r = await client.post(
                    "/api/v1/competition/mappings/propose",
                    json={"min_score": 0.4, "max_per_product": 3},
                )
                assert r.status_code == 200, r.text
                proposed = r.json()
                assert proposed["created"] >= 1
                assert proposed["considered_products"] >= 1

                mappings = (await client.get("/api/v1/competition/mappings")).json()
                mine = [m for m in mappings if m.get("internal_sku") == f"INT-{tag}"]
                assert mine, mappings
                assert mine[0]["approval_status"] == "pending"
                assert mine[0]["score"] is not None

                r = await client.post(
                    "/api/v1/competition/prices/import",
                    json={
                        "rows": [
                            {
                                "competitor_sku": f"CMP-{tag}",
                                "price": 999.5,
                                "observed_at": datetime.now(timezone.utc).isoformat(),
                                "channel": "web",
                            }
                        ]
                    },
                )
                assert r.status_code == 200, r.text
                assert r.json()["created"] == 1

                prices = (await client.get("/api/v1/competition/prices")).json()
                assert any(
                    p.get("competitor_sku") == f"CMP-{tag}" and float(p["price"]) == 999.5
                    for p in prices
                )

                r = await client.post(
                    "/api/v1/competition/mappings/propose",
                    json={"min_score": 0.4, "max_per_product": 3},
                )
                assert r.status_code == 200, r.text
                assert r.json()["skipped_existing"] >= 1
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous
            await seed.close()
            await outer.rollback()
