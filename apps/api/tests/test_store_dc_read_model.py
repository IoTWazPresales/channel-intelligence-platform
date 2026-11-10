"""Units 3 to 7: grain, served accounts, needs, both lead-time legs, suggestions only."""

from datetime import date, timedelta

import pytest

from app.services.store_dc.candidates import (
    decide_candidate,
    refresh_candidates,
    served_customer_ids,
    set_served_accounts,
)
from app.services.store_dc.read_model import build_customer_view
from app.services.store_dc.rules import COLLAPSED_NOTE, NO_HISTORY
from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


def _line(view: dict, site: str | None, product_id: int) -> dict:
    blocks = view["sites"] if site else [view["account"]]
    for block in blocks:
        if site is not None and block["site_label"] != site:
            continue
        for line in block["lines"]:
            if line["product_id"] == product_id:
                return line
    raise AssertionError(site)


def test_account_with_no_site_has_no_dc_section(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=None)
    hub = world.code("SDC-OTHER")
    world.deliveries(customer, distributor, hub, 5)
    world.db.flush()
    view = build_customer_view(world.db, world.tenant, customer.id)
    assert view["grain"] == "account"
    assert view["dc_sections"] == []
    assert view["sites"] == []
    assert view["account"]["site_label"] is None
    line = _line(view, None, product.id)
    assert line["need_units"] == 40
    assert line["lead_time_label"] == NO_HISTORY
    assert view["lead_times"][0]["onward"]["median_days"] is None
    assert view["lead_times"][0]["inbound"]["median_days"] is None
    assert view["cover"]["target_weeks"] == 6
    assert view["cover"]["min_weeks"] == 4
    assert view["cover"]["source"] == "fallback"


def test_two_stores_without_a_dc_keep_their_own_labels(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    north = world.code("SDC-SITE-A")
    south = world.code("SDC-SITE-B")
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=north)
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=south)
    world.weeks(customer, product, [1], soh=1, site=None)
    world.deliveries(customer, distributor, north, 5)
    confirm = date(2026, 3, 1)
    world.shipment(customer=customer, distributor=distributor, ship_to=south, confirm=confirm)
    world.shipment(
        customer=customer,
        distributor=distributor,
        ship_to=south,
        confirm=confirm + timedelta(days=1),
        pod=confirm - timedelta(days=2),
    )
    world.db.flush()
    view = build_customer_view(world.db, world.tenant, customer.id)
    assert view["dc_sections"] == []
    assert view["grain"] == "store"
    labels = {site["site_label"] for site in view["sites"]}
    assert labels == {north, south}
    assert customer.name not in labels
    assert view["collapsed_grain"]["note"] == COLLAPSED_NOTE
    assert _line(view, north, product.id)["need_units"] == 60
    assert _line(view, north, product.id)["lead_time_label"] == "lead time: 14 days"
    south_line = _line(view, south, product.id)
    assert south_line["need_units"] == 40
    assert south_line["lead_time_label"] == NO_HISTORY
    onward = view["lead_times"][0]["onward"]
    assert onward["median_days"] is None
    assert onward["lead_time_label"] == NO_HISTORY
    inbound_by_site = {row["receiving_site"]: row["inbound"]["median_days"] for row in view["lead_times"]}
    assert inbound_by_site[north.casefold()] == 14
    assert inbound_by_site[south.casefold()] is None


def test_four_deliveries_stay_on_cover_only(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=site)
    world.deliveries(customer, distributor, site, 4)
    world.db.flush()
    view = build_customer_view(world.db, world.tenant, customer.id)
    line = _line(view, site, product.id)
    assert line["need_units"] == 40
    assert line["lead_time_label"] == NO_HISTORY


def test_confirmed_dc_serves_two_accounts_and_stock_is_once(world: World):
    owner = world.customer("SDC-C1")
    other = world.customer("SDC-C2")
    distributor = world.distributor()
    product = world.product()
    hub = world.code("SDC-HUB-1")
    north = world.code("SDC-SITE-A")
    south = world.code("SDC-SITE-B")
    world.weeks(owner, product, [0, 0, 0, 0], soh=50, site=hub)
    world.weeks(owner, product, [10, 10, 10, 10], soh=20, site=north)
    world.weeks(other, product, [10, 10, 10, 10], soh=20, site=south)
    world.deliveries(owner, distributor, hub, 5)
    world.db.flush()
    refresh_candidates(world.db, world.tenant)
    from app.models.store_dc import SiteCandidate
    from sqlalchemy import select

    candidate = world.db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub)
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")
    set_served_accounts(world.db, world.tenant, candidate.id, [other.id])
    view = build_customer_view(world.db, world.tenant, owner.id)
    assert len(view["dc_sections"]) == 1
    section = view["dc_sections"][0]
    assert section["stock_on_hand"] == 50
    assert {row["customer_id"] for row in section["serves"]} == {owner.id, other.id}
    labels = {store["site_label"] for store in section["stores"]}
    assert labels == {north, south}
    assert owner.name not in labels and other.name not in labels
    assert all(store["supply"] == "customer_dc" for store in section["stores"])
    assert all(line["lead_time_label"] == NO_HISTORY for store in section["stores"] for line in store["lines"])
    assert all(line["need_units"] == 40 for store in section["stores"] for line in store["lines"])
    assert section["onward"]["median_days"] is None
    assert section["lead_time"]["median_days"] == 14
    assert section["need_from_distributor"][0]["stock_on_hand"] == 50
    other_view = build_customer_view(world.db, world.tenant, other.id)
    assert other_view["dc_sections"][0]["stock_on_hand"] == 50


def test_served_accounts_save_from_owner_context_preserves_extra_served_links(world: World):
    """B1: saving while the board shows only the owner checkbox must not drop other links."""
    owner = world.customer("SDC-C1")
    other = world.customer("SDC-C2")
    third = world.customer("SDC-C3")
    distributor = world.distributor()
    product = world.product()
    hub = world.code("SDC-HUB-1")
    site = world.code("SDC-SITE-A")
    world.weeks(owner, product, [0, 0, 0, 0], soh=50, site=hub)
    world.weeks(other, product, [10, 10, 10, 10], soh=20, site=site)
    world.weeks(third, product, [10, 10, 10, 10], soh=20, site=site)
    world.deliveries(owner, distributor, hub, 5)
    world.db.flush()
    refresh_candidates(world.db, world.tenant)
    from app.models.store_dc import SiteCandidate
    from sqlalchemy import select

    candidate = world.db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub)
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")
    set_served_accounts(world.db, world.tenant, candidate.id, [other.id, third.id])
    assert set(served_customer_ids(world.db, world.tenant, candidate)) == {owner.id, other.id, third.id}

    # Narrow visible set (only owner had a checkbox row); payload omits other and third — merge must keep them.
    set_served_accounts(
        world.db,
        world.tenant,
        candidate.id,
        [owner.id],
        context_customer_id=owner.id,
        visible_customer_ids=[owner.id],
    )
    assert set(served_customer_ids(world.db, world.tenant, candidate)) == {owner.id, other.id, third.id}

    # Steward sees every linked account in checkboxes — may remove one explicitly.
    set_served_accounts(
        world.db,
        world.tenant,
        candidate.id,
        [owner.id, third.id],
        context_customer_id=other.id,
        visible_customer_ids=[owner.id, other.id, third.id],
    )
    assert set(served_customer_ids(world.db, world.tenant, candidate)) == {owner.id, third.id}


def test_served_accounts_save_rejects_context_not_linked_to_site(world: World):
    owner = world.customer("SDC-C1")
    stranger = world.customer("SDC-CX")
    distributor = world.distributor()
    product = world.product()
    hub = world.code("SDC-HUB-1")
    world.weeks(owner, product, [0, 0, 0, 0], soh=50, site=hub)
    world.deliveries(owner, distributor, hub, 5)
    world.db.flush()
    refresh_candidates(world.db, world.tenant)
    from app.models.store_dc import SiteCandidate
    from sqlalchemy import select

    candidate = world.db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub)
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")
    with pytest.raises(ValueError, match="not allowed until"):
        set_served_accounts(
            world.db,
            world.tenant,
            candidate.id,
            [stranger.id],
            context_customer_id=stranger.id,
            visible_customer_ids=[stranger.id],
        )


def test_slow_and_unsold_are_labels_only(world: World):
    customer = world.customer("SDC-C")
    product_slow = world.product("SDC-SLOW")
    product_unsold = world.product("SDC-UNSOLD")
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product_slow, [10, 10, 10, 10], soh=120, site=site)
    world.weeks(customer, product_unsold, [0, 0, 0, 0], soh=5, site=site)
    world.db.flush()
    before = world.counts()
    view = build_customer_view(world.db, world.tenant, customer.id)
    slow = _line(view, site, product_slow.id)
    unsold = _line(view, site, product_unsold.id)
    assert slow["slow"] is True and slow["unsold"] is False
    assert unsold["unsold"] is True and unsold["slow"] is False
    assert slow["suggestions"] == ["promote", "move", "return"]
    assert unsold["suggestions"] == ["promote", "move", "return"]
    assert slow["suggestion_executed"] is False
    assert slow["executed_actions"] == []
    assert world.counts()[:2] == before[:2]


def test_an_open_stock_action_marks_that_suggestion_executed(world: World):
    from uuid import uuid4

    from app.models.cpor import CporCase, CporCaseLine

    customer = world.customer("SDC-C")
    product = world.product("SDC-SLOW")
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product, [10, 10, 10, 10], soh=120, site=site)
    case = CporCase(
        case_code=f"SDC-{uuid4().hex[:12]}",
        case_name="Move aged stock",
        tenant_id=world.tenant,
        customer_id=customer.id,
        promotion_type="Stock PP (In-Direct)",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 3, 31),
        status="draft",
        origin="stock_action",
        notes="stock_action=move;not_a_support_claim=true",
        intelligence_exclude=True,
        currency_code="ZAR",
        channel="reseller",
    )
    world.db.add(case)
    world.db.flush()
    world.db.add(
        CporCaseLine(
            case_id=case.id,
            product_id=product.id,
            srp=100,
            vat_rate=0.15,
            dealer_margin_pct=0.12,
            estimate_qty=120,
            window_start=case.window_start,
            window_end=case.window_end,
        )
    )
    world.db.flush()
    before = world.counts()
    view = build_customer_view(world.db, world.tenant, customer.id)
    line = _line(view, site, product.id)
    assert line["suggestion_executed"] is True
    assert line["executed_actions"] == ["move"]
    assert line["suggestions"] == ["promote", "move", "return"]
    assert world.counts()[:2] == before[:2]


def test_approved_competitor_join_executes(world: World):
    from sqlalchemy import text

    from app.services.cpor.promo_plan_builder import _approved_competitor_prices

    name = world.db.execute(text("select current_database()")).scalar()
    print("current_database()", name)
    assert name == "cip_test"
    prices = _approved_competitor_prices(world.db, -1)
    assert prices == []


def test_customer_can_override_the_suggestion_thresholds(world: World):
    customer = world.customer("SDC-C", slow=3, unsold=2)
    product = world.product()
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product, [10, 10, 0, 0], soh=120, site=site)
    world.db.flush()
    line = _line(build_customer_view(world.db, world.tenant, customer.id), site, product.id)
    # 120 / 5 = 24 weeks. Target 6. Multiple 3 means slow at 18, so this is slow.
    # Last 2 weeks are zero, so the override window marks it unsold. The default 4-week window would not.
    assert line["weeks_of_cover"] == 24
    assert line["slow"] is True
    assert line["unsold"] is True
