"""Unit 8: one dot per store per customer. A pin is the only location this module creates."""

import csv
from pathlib import Path

import pytest

from sqlalchemy import func, select, text

from app.models.dimensions import CustomerLocation
from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import decide_candidate, refresh_candidates
from app.services.store_dc.map import build_store_map, drop_pin
from app.services.store_dc.place_name import (
    normalise_place,
    place_name_from_raw,
    suggest_store_location,
)

_PLACES = Path(__file__).resolve().parents[1] / "app" / "services" / "store_dc" / "data" / "za_populated_places.csv"
_LICENCE = _PLACES.with_name("ZA_PLACES_LICENCE.txt")


def _suggesting_place() -> dict[str, str]:
    """A bundled place whose own name suggests that one place and nothing else."""
    groups: dict[str, list[dict[str, str]]] = {}
    with _PLACES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            groups.setdefault(normalise_place(row["name"]), []).append(row)
    for rows in groups.values():
        name = rows[0]["name"]
        if any(mark in name for mark in (",", ";", "/", "-")):
            continue
        hit = suggest_store_location(name)
        if hit["outcome"] == "suggest" and hit["place"] == name:
            return rows[0]
    raise AssertionError("bundled place list has no unique place name")


def _ambiguous_place_name() -> str:
    groups: dict[str, set[str]] = {}
    with _PLACES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            groups.setdefault(normalise_place(row["name"]), set()).add(row["geonameid"])
    for key, ids in groups.items():
        if len(ids) < 2:
            continue
        hit = suggest_store_location(key)
        if hit["outcome"] == "manual" and hit["reason"] == "multiple":
            return key
    raise AssertionError("bundled place list has no repeated place name")

from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


def test_a_store_without_coordinates_is_not_pinned_and_a_pin_is_remembered(world: World):
    first = world.customer("SDC-C1")
    second = world.customer("SDC-C2")
    product = world.product()
    shared = world.code("SDC-SITE-A")
    loose = world.code("SDC-SITE-B")
    world.weeks(first, product, [4, 6], soh=4, site=shared)
    world.weeks(second, product, [1, 1], soh=9, site=shared)
    world.weeks(first, product, [2], soh=2, site=loose)
    world.db.flush()
    before = build_store_map(world.db, world.tenant)
    assert len(before["stores"]) == 3
    assert all(store["pinned"] is False and store["latitude"] is None for store in before["stores"])
    assert {store["customer_id"] for store in before["stores"] if store["site_label"] == shared} == {first.id, second.id}
    locations_before = world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
    pinned = drop_pin(
        world.db,
        tenant_id=world.tenant,
        customer_id=first.id,
        site_label=shared,
        latitude=1.5,
        longitude=2.5,
        actor="steward-test",
    )
    assert pinned["pinned"] is True
    assert pinned["latitude"] == 1.5
    assert pinned["longitude"] == 2.5
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == locations_before + 1
    other = drop_pin(
        world.db,
        tenant_id=world.tenant,
        customer_id=second.id,
        site_label=shared,
        latitude=1.5,
        longitude=2.5,
        actor="steward-test",
    )
    assert other["customer_id"] != pinned["customer_id"]
    again = build_store_map(world.db, world.tenant)
    dots = [store for store in again["stores"] if store["pinned"]]
    assert len(dots) == 2
    assert dots[0]["latitude"] == dots[1]["latitude"] == 1.5
    unpinned = [store for store in again["stores"] if not store["pinned"]]
    assert len(unpinned) == 1
    assert unpinned[0]["site_label"] == loose
    ratio = pinned["sell_through"]
    assert ratio == round(6 / (6 + 4), 4)
    with pytest.raises(LookupError):
        drop_pin(
            world.db,
            tenant_id=world.tenant,
            customer_id=first.id,
            site_label=world.code("SDC-MISSING"),
            latitude=1.5,
            longitude=2.5,
            actor="steward-test",
        )


def test_refresh_does_not_create_a_location_and_a_confirmed_dc_is_not_a_store_dot(world: World):
    customer = world.customer("SDC-C")
    distributor = world.distributor()
    product = world.product()
    hub = world.code("SDC-HUB-1")
    store = world.code("SDC-SITE-A")
    locations_before = world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
    world.weeks(customer, product, [0, 0], soh=9, site=hub)
    world.weeks(customer, product, [2, 2], soh=2, site=store)
    world.shipment(customer=customer, distributor=distributor, ship_to=hub)
    world.db.flush()
    created = refresh_candidates(world.db, world.tenant)
    assert created["locations_created"] == 0
    candidate = world.db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == world.tenant, SiteCandidate.site_label == hub)
    ).scalar_one()
    decide_candidate(world.db, world.tenant, candidate.id, "confirm", "steward-test")
    payload = build_store_map(world.db, world.tenant, [customer.id])
    assert [row["site_label"] for row in payload["stores"]] == [store]
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == locations_before


def test_place_name_columns_do_not_use_the_store_code():
    assert place_name_from_raw({"Site Name": "North Shed", "col_10": "Ignore Me"}) == "North Shed"
    assert place_name_from_raw({"Site Name": "  ", "Calendar Day": "2026-01-05", "col_10": "East Yard", "col_11": "Ignore Me"}) == "East Yard"
    assert place_name_from_raw({"Sales U TY 022.2026": "1", "col_10": "Ignore Me", "col_11": "West Dock"}) == "West Dock"
    assert place_name_from_raw({"Site": "CODE-1"}) is None


def test_place_name_is_read_from_the_source_row_and_the_code_stays_the_key(world: World):
    database = world.db.execute(text("select current_database()")).scalar_one()
    print("current_database()", database)
    assert database == "cip_test"
    customer = world.customer("SDC-C")
    product = world.product()
    named = world.code("SDC-CODE-N")
    day = world.code("SDC-CODE-D")
    band = world.code("SDC-CODE-B")
    world.weeks(
        customer,
        product,
        [3],
        soh=6,
        site=named,
        raw={"Site Name": "North Shed", "Site Code": named, "col_10": "Ignore Me"},
    )
    world.weeks(
        customer,
        product,
        [3],
        soh=6,
        site=day,
        raw={"Calendar Day": "2026-01-05", "Site": day, "col_10": "East Yard", "col_11": "Ignore Me"},
    )
    world.weeks(
        customer,
        product,
        [3],
        soh=6,
        site=band,
        raw={"Sales U TY 022.2026": "1", "Site": band, "col_10": "Ignore Me", "col_11": "West Dock"},
    )
    world.db.flush()
    payload = build_store_map(world.db, world.tenant, [customer.id])
    by_code = {row["site_label"]: row for row in payload["stores"]}
    assert set(by_code) == {named, day, band}
    assert by_code[named]["place_name"] == "North Shed"
    assert by_code[day]["place_name"] == "East Yard"
    assert by_code[band]["place_name"] == "West Dock"
    for row in by_code.values():
        assert row["last_week_units"] == 3
        assert row["stock_on_hand"] == 6
        assert row["sell_through"] == round(3 / (3 + 6), 4)
        assert row["place_name"] != row["site_label"]
        assert row["location_suggestion"]["outcome"] == "manual"
        assert row["location_suggestion"]["reason"] == "none"
        assert row["latitude"] is None


def test_place_suggestion_is_exact_and_a_miss_or_a_clash_is_manual():
    licence = _LICENCE.read_text(encoding="utf-8")
    assert "GeoNames" in licence
    assert "CC BY" in licence
    source = Path(suggest_store_location.__code__.co_filename).read_text(encoding="utf-8")
    assert "urlopen" not in source
    assert "requests" not in source
    place = _suggesting_place()
    other = None
    with _PLACES.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["geonameid"] == place["geonameid"]:
                continue
            hit = suggest_store_location(row["name"])
            if hit["outcome"] == "suggest" and hit["place"] != place["name"] and "-" not in row["name"]:
                other = row
                break
    assert other is not None
    suggested = suggest_store_location(f"Branch - {place['name']}")
    assert suggested["outcome"] == "suggest"
    assert suggested["place"] == place["name"]
    assert suggested["latitude"] == pytest.approx(float(place["latitude"]))
    assert suggested["longitude"] == pytest.approx(float(place["longitude"]))
    assert suggested["licence"] == "GeoNames CC BY 4.0"
    folded = suggest_store_location(place["name"].upper())
    assert folded["outcome"] == "suggest"
    assert folded["place"] == place["name"]
    squashed = place["name"].replace(" ", "")
    if normalise_place(squashed) != normalise_place(place["name"]):
        assert suggest_store_location(squashed)["outcome"] == "manual"
    assert suggest_store_location("ZZ-NO-SUCH-PLACE")["reason"] == "none"
    assert suggest_store_location(_ambiguous_place_name())["reason"] == "multiple"
    clash = suggest_store_location(f"{place['name']} - {other['name']}")
    assert clash["outcome"] == "manual"
    assert clash["reason"] == "multiple"
    assert suggest_store_location(None)["reason"] == "none"


def test_a_suggestion_is_not_saved_until_the_steward_pins_it(world: World):
    database = world.db.execute(text("select current_database()")).scalar_one()
    print("current_database()", database)
    assert database == "cip_test"
    place = _suggesting_place()
    customer = world.customer("SDC-C")
    product = world.product()
    label = f"{world.code('SDC-BRANCH')} - {place['name']}"
    locations_before = world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
    world.weeks(customer, product, [2], soh=2, site=label)
    world.db.flush()
    payload = build_store_map(world.db, world.tenant, [customer.id])
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == locations_before
    row = payload["stores"][0]
    assert row["site_label"] == label
    assert row["pinned"] is False
    assert row["latitude"] is None
    assert row["longitude"] is None
    suggestion = row["location_suggestion"]
    assert suggestion["outcome"] == "suggest"
    assert suggestion["place"] == place["name"]
    pinned = drop_pin(
        world.db,
        tenant_id=world.tenant,
        customer_id=customer.id,
        site_label=label,
        latitude=suggestion["latitude"],
        longitude=suggestion["longitude"],
        actor="steward-test",
    )
    assert pinned["pinned"] is True
    assert pinned["latitude"] == pytest.approx(suggestion["latitude"])
    assert pinned["longitude"] == pytest.approx(suggestion["longitude"])
    assert pinned["location_suggestion"] is None
    assert world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one() == locations_before + 1
