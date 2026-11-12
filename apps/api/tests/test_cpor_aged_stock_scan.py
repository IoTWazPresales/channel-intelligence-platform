"""The aged-stock scan reads only customers with stock evidence (cip_test, rolled back).

Same suggestions as the old every-customer scan, with bounded work: a customer
with no reported stock builds no view, and the tenant-wide lead index is built once.
"""

from __future__ import annotations

import app.services.store_dc.read_model as read_model
import app.services.store_dc.stock_actions as actions
from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import (
    decide_candidate,
    refresh_candidates,
    set_served_accounts,
)
from app.services.store_dc.read_model import build_customer_view
from sqlalchemy import select
from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


def _build(world: World) -> dict:
    owner = world.customer("SCAN-OWN")
    other = world.customer("SCAN-OTH")
    slow = world.customer("SCAN-SLOW")
    empty = [world.customer(f"SCAN-E{i}") for i in range(5)]
    no_stock = world.customer("SCAN-NOSOH")
    distributor = world.distributor()
    product = world.product()
    hub = world.code("SCAN-HUB")
    north = world.code("SCAN-NORTH")
    south = world.code("SCAN-SOUTH")
    world.weeks(owner, product, [0, 0, 0, 0], soh=50, site=hub)
    world.weeks(owner, product, [10, 10, 10, 10], soh=20, site=north)
    world.weeks(other, product, [10, 10, 10, 10], soh=20, site=south)
    world.weeks(slow, product, [10, 10, 10, 10], soh=120, site=north)
    world.weeks(no_stock, product, [10, 10, 10, 10], soh=None, site=north)
    world.deliveries(owner, distributor, hub, 5)
    world.db.flush()
    refresh_candidates(world.db, world.tenant)
    candidate = world.db.execute(
        select(SiteCandidate).where(
            SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub
        )
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")
    set_served_accounts(world.db, world.tenant, candidate.id, [other.id])
    return {"owner": owner, "other": other, "slow": slow, "empty": empty, "no_stock": no_stock}


def _signature(rows: list[dict]) -> list[tuple]:
    return sorted(
        (
            int(row["customer_id"]),
            int(row["product_id"]),
            row.get("site_label"),
            tuple(row.get("suggestions") or ()),
            row.get("stock_on_hand"),
            row.get("weeks_of_cover"),
            bool(row.get("slow")),
            bool(row.get("unsold")),
        )
        for row in rows
    )


def _every_customer_scan(world: World) -> list[dict]:
    """The scan as it was: a customer view for every active customer."""
    rows: list[dict] = []
    for cid in actions._customer_ids(world.db, tenant_id=world.tenant, customer_id=None):
        view = build_customer_view(world.db, world.tenant, cid)
        rows.extend(actions._suggestion_rows(view, customer_id=cid))
    return rows


def test_scan_gives_the_same_suggestions_as_the_every_customer_scan(world: World):
    _build(world)
    reference = _signature(_every_customer_scan(world))
    scanned, truncated = actions._collect_aged_stock(world.db, tenant_id=world.tenant, limit=None)
    assert truncated is False
    assert reference, "the fixture must produce suggestions"
    assert _signature(scanned) == reference


def test_scan_skips_customers_without_stock_and_builds_one_lead_index(world: World, monkeypatch):
    people = _build(world)
    viewed: list[int] = []
    lead_builds: list[int] = []
    real_view = actions.build_customer_view
    real_lead = read_model._lead_index

    def view(db, tenant_id, customer_id, **kwargs):
        viewed.append(int(customer_id))
        return real_view(db, tenant_id, customer_id, **kwargs)

    def lead(db, tenant_id, min_deliveries):
        lead_builds.append(1)
        return real_lead(db, tenant_id, min_deliveries)

    monkeypatch.setattr(actions, "build_customer_view", view)
    monkeypatch.setattr(read_model, "_lead_index", lead)
    actions._collect_aged_stock(world.db, tenant_id=world.tenant, limit=None)

    wanted = {people["owner"].id, people["other"].id, people["slow"].id}
    assert set(viewed) == wanted
    assert len(viewed) == 3
    assert not ({c.id for c in people["empty"]} & set(viewed))
    assert people["no_stock"].id not in viewed
    assert len(lead_builds) == 1


def test_a_named_customer_is_still_viewed_even_without_stock(world: World, monkeypatch):
    people = _build(world)
    viewed: list[int] = []
    real_view = actions.build_customer_view

    def view(db, tenant_id, customer_id, **kwargs):
        viewed.append(int(customer_id))
        return real_view(db, tenant_id, customer_id, **kwargs)

    monkeypatch.setattr(actions, "build_customer_view", view)
    rows, _ = actions._collect_aged_stock(
        world.db, tenant_id=world.tenant, customer_id=people["empty"][0].id, limit=None
    )
    assert rows == []
    assert viewed == [people["empty"][0].id]


def test_limit_still_truncates_when_rows_remain(world: World):
    _build(world)
    total = len(_every_customer_scan(world))
    assert total >= 2
    rows, truncated = actions._collect_aged_stock(world.db, tenant_id=world.tenant, limit=total - 1)
    assert len(rows) == total - 1
    assert truncated is True
    rows, _truncated = actions._collect_aged_stock(world.db, tenant_id=world.tenant, limit=total)
    assert len(rows) == total
