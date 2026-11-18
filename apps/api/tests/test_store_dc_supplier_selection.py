"""W1-A: lead-time samples are deliveries, and each DC SKU gets its own supplier (alignment D4)."""

from datetime import date, timedelta

from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import decide_candidate, refresh_candidates
from app.services.store_dc.read_model import build_customer_view
from app.services.store_dc.rules import NO_HISTORY
from sqlalchemy import select
from tests.store_dc_fixture import WEEK0, World

pytest_plugins = ("tests.store_dc_fixture",)


def _site_line(view: dict, site: str, product_id: int) -> dict:
    for block in view["sites"]:
        if block["site_label"] == site:
            for line in block["lines"]:
                if line["product_id"] == product_id:
                    return line
    raise AssertionError(site)


def test_lines_of_one_delivery_number_count_once(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=site)
    confirm = date(2026, 3, 1)
    for index in range(6):
        world.shipment(
            customer=customer, distributor=distributor, ship_to=site,
            confirm=confirm + timedelta(days=index % 2), pod=confirm + timedelta(days=14),
            delivery_no="DLV-ONE",
        )
    world.db.flush()
    view = build_customer_view(world.db, world.tenant, customer.id)
    line = _site_line(view, site, product.id)
    assert line["lead_time_label"] == NO_HISTORY
    inbound = {row["receiving_site"]: row["inbound"] for row in view["lead_times"]}[site.casefold()]
    assert inbound["sample_count"] == 1
    assert inbound["max_days"] == 14


def test_lines_without_delivery_number_group_by_order_and_dates(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=site)
    confirm = date(2026, 3, 1)
    for _ in range(5):
        world.shipment(customer=customer, distributor=distributor, ship_to=site,
                       confirm=confirm, pod=confirm + timedelta(days=14), order_no="ORD-1")
    world.db.flush()
    view = build_customer_view(world.db, world.tenant, customer.id)
    assert _site_line(view, site, product.id)["lead_time_label"] == NO_HISTORY


def test_five_distinct_deliveries_still_learn_the_lead_time(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    site = world.code("SDC-SITE-A")
    world.weeks(customer, product, [10, 10, 10, 10], soh=20, site=site)
    confirm = date(2026, 3, 1)
    for index in range(5):
        world.shipment(customer=customer, distributor=distributor, ship_to=site,
                       confirm=confirm + timedelta(days=index),
                       pod=confirm + timedelta(days=index + 14),
                       delivery_no=f"DLV-{index}")
    world.db.flush()
    view = build_customer_view(world.db, world.tenant, customer.id)
    assert _site_line(view, site, product.id)["lead_time_label"] == "lead time: 14 days"


def _confirmed_hub(world: World, owner, hub: str) -> None:
    refresh_candidates(world.db, world.tenant)
    candidate = world.db.execute(
        select(SiteCandidate).where(
            SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub
        )
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")


def test_dc_supplier_is_chosen_per_sku_by_stock_then_lead_time(world: World):
    owner = world.customer("SDC-C1")
    fast = world.distributor("SDC-DA")
    stocked = world.distributor("SDC-DB")
    stocked_sku = world.product("SDC-SKU-A")
    unstocked_sku = world.product("SDC-SKU-B")
    hub = world.code("SDC-HUB-1")
    store = world.code("SDC-SITE-A")
    for product in (stocked_sku, unstocked_sku):
        world.weeks(owner, product, [0, 0, 0, 0], soh=5, site=hub)
        world.weeks(owner, product, [10, 10, 10, 10], soh=0, site=store)
    # More shipment lines from the fast distributor (old ranking would always pick it).
    world.deliveries(owner, fast, hub, 8, days=7)
    world.deliveries(owner, stocked, hub, 5, days=21)
    world.distributor_stock(fast, stocked_sku, 0, date(2026, 3, 20))
    world.distributor_stock(stocked, stocked_sku, 40, date(2026, 3, 20))
    world.db.flush()
    _confirmed_hub(world, owner, hub)
    view = build_customer_view(world.db, world.tenant, owner.id)
    section = view["dc_sections"][0]
    rows = {row["product_id"]: row for row in section["need_from_distributor"]}

    a = rows[stocked_sku.id]
    assert a["supplier"]["distributor_id"] == stocked.id
    assert a["supplier"]["sku_stock_on_hand"] == 40
    assert a["lead_time_label"] == "lead time: 21 days"
    assert [o["distributor_id"] for o in a["supplier_options"]] == [stocked.id, fast.id]

    b = rows[unstocked_sku.id]
    # No distributor reports stock of this SKU: the shorter learned lead time wins.
    assert b["supplier"]["distributor_id"] == fast.id
    assert b["supplier"]["sku_stock_on_hand"] is None
    assert b["supplier"]["stock_note"] == "stock not reported"
    assert b["lead_time_label"] == "lead time: 7 days"
    # The need line reports the chosen supplier's lead time (DC sells nothing here, so it adds 0).
    assert a["supplier"]["lead_time_weeks"] == 3.0


def test_dc_supplier_stock_is_per_sku_not_distributor_total(world: World):
    owner = world.customer("SDC-C1")
    dist = world.distributor("SDC-DA")
    sku = world.product("SDC-SKU-A")
    other_sku = world.product("SDC-SKU-B")
    hub = world.code("SDC-HUB-1")
    store = world.code("SDC-SITE-A")
    world.weeks(owner, sku, [0, 0, 0, 0], soh=5, site=hub)
    world.weeks(owner, sku, [10, 10, 10, 10], soh=0, site=store)
    world.deliveries(owner, dist, hub, 5)
    world.distributor_stock(dist, other_sku, 500, date(2026, 3, 20))
    world.db.flush()
    _confirmed_hub(world, owner, hub)
    view = build_customer_view(world.db, world.tenant, owner.id)
    row = view["dc_sections"][0]["need_from_distributor"][0]
    assert row["supplier"]["distributor_id"] == dist.id
    assert row["supplier"]["sku_stock_on_hand"] is None


def _confirm_owned_hub(world: World, owner, hub: str) -> None:
    refresh_candidates(world.db, world.tenant)
    candidate = world.db.execute(
        select(SiteCandidate).where(
            SiteCandidate.tenant_id == world.tenant,
            SiteCandidate.site_label == hub,
            SiteCandidate.customer_id == owner.id,
        )
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")


def test_unrelated_customer_with_the_same_dc_label_is_not_a_supplier(world: World):
    """Codex review of PR #102 (B1): supplier evidence keeps the DC's customer identity."""
    owner = world.customer("SDC-C1")
    stranger = world.customer("SDC-C2")
    own_dist = world.distributor("SDC-DA")
    other_dist = world.distributor("SDC-DX")
    sku = world.product("SDC-SKU-A")
    hub = world.code("SDC-HUB-1")
    store = world.code("SDC-SITE-A")
    world.weeks(owner, sku, [5, 5, 5, 5], soh=5, site=hub)
    world.weeks(owner, sku, [10, 10, 10, 10], soh=0, site=store)
    # The stranger has its own site with the same label, served by another distributor
    # that is stocked and fast.
    world.weeks(stranger, sku, [1, 1, 1, 1], soh=3, site=hub)
    world.deliveries(owner, own_dist, hub, 5, days=21)
    world.deliveries(stranger, other_dist, hub, 9, days=3)
    world.distributor_stock(other_dist, sku, 100, date(2026, 3, 20))
    world.db.flush()
    _confirm_owned_hub(world, owner, hub)
    view = build_customer_view(world.db, world.tenant, owner.id)
    section = next(s for s in view["dc_sections"] if s["customer_id"] == owner.id)
    row = {r["product_id"]: r for r in section["need_from_distributor"]}[sku.id]
    assert [o["distributor_id"] for o in row["supplier_options"]] == [own_dist.id]
    assert row["supplier"]["distributor_id"] == own_dist.id
    assert row["lead_time_label"] == "lead time: 21 days"
    assert section["lead_time"]["sample_count"] == 5
    # The DC sells 5 a week, so the chosen supplier's 3-week lead time is in the need.
    target = row["need_units"]
    assert target is not None and target > 0


def test_chosen_supplier_lead_time_changes_the_dc_need(world: World):
    owner = world.customer("SDC-C1", target=2)
    slow = world.distributor("SDC-DA")
    sku = world.product("SDC-SKU-A")
    hub = world.code("SDC-HUB-1")
    store = world.code("SDC-SITE-A")
    world.weeks(owner, sku, [7, 7, 7, 7], soh=10, site=hub)
    world.weeks(owner, sku, [0, 0, 0, 0], soh=50, site=store)
    world.deliveries(owner, slow, hub, 5, days=14)
    world.db.flush()
    _confirm_owned_hub(world, owner, hub)
    view = build_customer_view(world.db, world.tenant, owner.id)
    row = view["dc_sections"][0]["need_from_distributor"][0]
    assert row["lead_time_label"] == "lead time: 14 days"
    # 7/week x (2 target + 2 lead weeks) - 10 on hand = 18; without the lead time it would be 4.
    assert row["need_units"] == 18.0
    assert row["need_reason"] == "stores_plus_cover_and_lead_time"


def test_rate_uses_consecutive_calendar_weeks_not_the_last_four_reports(world: World):
    customer = world.customer("SDC-C")
    product = world.product()
    site = world.code("SDC-SITE-A")
    for index, units in ((0, 100), (1, 100), (4, 10), (5, 10)):
        world.sell(customer, product, WEEK0 + timedelta(weeks=index), units,
                   soh=20 if index == 5 else None, site=site)
    world.db.flush()
    line = _site_line(build_customer_view(world.db, world.tenant, customer.id), site, product.id)
    # Weeks 2-5 are the last four calendar weeks; weeks 2 and 3 were not reported, so the
    # rate is the two reported weeks (10/week), not (100+100+10+10)/4 = 55.
    assert line["weekly_rate"] == 10.0


def test_daily_reports_give_a_weekly_rate(world: World):
    customer = world.customer("SDC-C")
    product = world.product()
    site = world.code("SDC-SITE-A")
    for offset in range(28):
        world.sell(customer, product, WEEK0 + timedelta(days=offset), 2,
                   soh=30 if offset == 27 else None, site=site,
                   period_type="daily", period_grain="day")
    world.db.flush()
    line = _site_line(build_customer_view(world.db, world.tenant, customer.id), site, product.id)
    assert line["weekly_rate"] == 14.0
    assert line["weeks_of_cover"] == round(30 / 14, 2)


def test_monthly_reports_give_a_weekly_rate_without_double_counting(world: World):
    customer = world.customer("SDC-C")
    product = world.product()
    site = world.code("SDC-SITE-A")
    # January: 310 units = 10 a day.
    world.sell(customer, product, date(2026, 1, 1), 310, site=site,
               period_type="monthly", period_grain="month")
    world.db.flush()
    line = _site_line(build_customer_view(world.db, world.tenant, customer.id), site, product.id)
    assert line["weekly_rate"] == 70.0
    # A weekly report for Mon 26 Jan - Sun 1 Feb replaces the month on those days.
    world.sell(customer, product, date(2026, 1, 26), 7, soh=40, site=site)
    world.db.flush()
    line = _site_line(build_customer_view(world.db, world.tenant, customer.id), site, product.id)
    # 5 Jan - 1 Feb: 21 month days x 10 + 7 from the week = 217 over 28 days.
    assert line["weekly_rate"] == 54.25

