"""Unit 8: one dot per store per customer. A pin is the only location this module creates."""

import csv
from pathlib import Path

import pytest
from app.models.dimensions import CustomerLocation
from app.models.store_dc import SiteCandidate
from app.services import tenant_settings
from app.services.store_dc.candidates import decide_candidate, refresh_candidates
from app.models.customer_report_config import CustomerReportConfig
from app.services.store_dc.map import build_store_map, confirm_pins, drop_pin
from app.services.store_dc.read_model import list_board_customers
from app.services.store_dc.place_name import (
    normalise_place,
    place_name_from_raw,
    place_table_for_country,
)
from app.services.store_dc.place_name import (
    suggest_store_location as _suggest,
)
from sqlalchemy import func, select, text

_PLACES = Path(__file__).resolve().parents[1] / "app" / "services" / "store_dc" / "data" / "za_populated_places.csv"
_LICENCE = _PLACES.with_name("ZA_PLACES_LICENCE.txt")
# Test data: the bundled places file under test is the ZA one, chosen through the country setting.
_ZA = place_table_for_country("ZA")


def suggest_store_location(label, **kwargs):
    return _suggest(label, table=_ZA, **kwargs)


def _country(world, code: str = "ZA") -> None:
    tenant_settings.set_setting(
        world.db,
        world.tenant,
        tenant_settings.KEY_TENANT_COUNTRY,
        {"code": code, "name": code},
        actor="test",
    )


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
        if hit["outcome"] == "suggest" and hit["place"] == name and not hit["ambiguous"]:
            return rows[0]
    raise AssertionError("bundled place list has no unique place name")


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
    _country(world)
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


def test_place_proposal_is_offline_licensed_and_a_miss_is_manual():
    licence = _LICENCE.read_text(encoding="utf-8")
    assert "GeoNames" in licence
    assert "CC BY" in licence
    source = Path(_suggest.__code__.co_filename).read_text(encoding="utf-8")
    assert "urlopen" not in source
    assert "requests" not in source
    place = _suggesting_place()
    suggested = suggest_store_location(f"Branch - {place['name']}")
    assert suggested["outcome"] == "suggest"
    assert suggested["place"] == place["name"]
    assert suggested["latitude"] == pytest.approx(float(place["latitude"]))
    assert suggested["longitude"] == pytest.approx(float(place["longitude"]))
    assert suggested["licence"] == "GeoNames CC BY 4.0"
    assert suggested["method"] in {"exact", "contained"}
    assert 0 < suggested["confidence"] <= 1
    folded = suggest_store_location(place["name"].upper())
    assert folded["outcome"] == "suggest"
    assert folded["place"] == place["name"]
    assert suggest_store_location("ZZ-NO-SUCH-PLACE")["reason"] == "none"
    assert suggest_store_location(None)["reason"] == "none"


def test_a_suggestion_is_not_saved_until_the_steward_pins_it(world: World):
    _country(world)
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


# --- L5: proposals for live-shaped labels, and the steward's confirm -------------------------


def _chain_label(customer, place: dict[str, str], suffix: str = "MALL") -> str:
    """A label shaped like the live ones: the customer's own name, the town, a generic word."""
    return f"{customer.name} {place['name'].upper()} {suffix}"


def _count_locations(world: World) -> int:
    return world.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()


def test_the_map_proposes_a_place_for_a_chain_shaped_label_and_writes_nothing(world: World):
    _country(world)
    place = _suggesting_place()
    customer = world.customer("SDC-C")
    product = world.product()
    label = _chain_label(customer, place)
    nothing = f"{customer.name} HEAD OFFICE WHOLESALE"
    before = _count_locations(world)
    world.weeks(customer, product, [2], soh=2, site=label)
    world.weeks(customer, product, [2], soh=2, site=nothing)
    world.db.flush()
    payload = build_store_map(world.db, world.tenant, [customer.id])
    by_label = {row["site_label"]: row for row in payload["stores"]}
    proposal = by_label[label]["location_suggestion"]
    assert proposal["outcome"] == "suggest"
    assert proposal["place"] == place["name"]
    assert proposal["method"] in {"exact", "contained"}
    assert 0 < proposal["confidence"] <= 1
    assert isinstance(proposal["alternatives"], list)
    assert proposal["latitude"] == pytest.approx(float(place["latitude"]))
    assert proposal["longitude"] == pytest.approx(float(place["longitude"]))
    assert by_label[nothing]["location_suggestion"]["outcome"] == "manual"
    assert all(row["pinned"] is False and row["latitude"] is None for row in payload["stores"])
    assert _count_locations(world) == before


def test_the_proposal_does_not_treat_the_customer_name_as_the_town(world: World):
    _country(world)
    place = _suggesting_place()
    # the customer is named like the town, so the town word in the label is the chain
    customer = world.customer(place["name"].upper().replace(" ", "-"))
    product = world.product()
    label = f"{customer.name} {place['name']} MALL"
    world.weeks(customer, product, [2], soh=2, site=label)
    world.db.flush()
    row = build_store_map(world.db, world.tenant, [customer.id])["stores"][0]
    assert row["location_suggestion"]["outcome"] == "manual"


def test_confirming_a_proposal_saves_the_proposed_coordinates_through_the_pin_write(world: World):
    _country(world)
    place = _suggesting_place()
    customer = world.customer("SDC-C")
    product = world.product()
    label = _chain_label(customer, place)
    world.weeks(customer, product, [3], soh=1, site=label)
    world.db.flush()
    before = _count_locations(world)
    out = confirm_pins(
        world.db,
        tenant_id=world.tenant,
        items=[{"customer_id": customer.id, "site_label": label}],
        actor="steward-test",
    )
    assert out["failed"] == []
    assert len(out["saved"]) == 1
    saved = out["saved"][0]
    assert saved["pinned"] is True
    assert saved["latitude"] == pytest.approx(float(place["latitude"]))
    assert saved["longitude"] == pytest.approx(float(place["longitude"]))
    assert _count_locations(world) == before + 1
    location = world.db.execute(
        select(CustomerLocation).where(CustomerLocation.customer_id == customer.id)
    ).scalar_one()
    assert location.confirmed_by == "steward-test"
    assert location.location_name == label
    # the next read has a pin and no proposal
    again = build_store_map(world.db, world.tenant, [customer.id])["stores"][0]
    assert again["pinned"] is True and again["location_suggestion"] is None


def test_an_edited_pin_is_saved_as_the_steward_sent_it_not_as_proposed(world: World):
    _country(world)
    place = _suggesting_place()
    customer = world.customer("SDC-C")
    product = world.product()
    label = _chain_label(customer, place)
    world.weeks(customer, product, [3], soh=1, site=label)
    world.db.flush()
    out = confirm_pins(
        world.db,
        tenant_id=world.tenant,
        items=[{"customer_id": customer.id, "site_label": label, "latitude": 1.25, "longitude": 2.5}],
        actor="steward-test",
    )
    assert out["saved"][0]["latitude"] == 1.25 and out["saved"][0]["longitude"] == 2.5
    # an edit may also move an existing pin
    moved = confirm_pins(
        world.db,
        tenant_id=world.tenant,
        items=[{"customer_id": customer.id, "site_label": label, "latitude": 3.0, "longitude": 4.0}],
        actor="steward-test",
    )
    assert moved["saved"][0]["latitude"] == 3.0
    assert _count_locations(world) == 1


def test_confirm_without_a_proposal_or_for_a_pinned_or_unknown_store_writes_nothing(world: World):
    _country(world)
    place = _suggesting_place()
    customer = world.customer("SDC-C")
    product = world.product()
    nothing = f"{customer.name} HEAD OFFICE WHOLESALE"
    pinned_label = _chain_label(customer, place)
    world.weeks(customer, product, [3], soh=1, site=nothing)
    world.weeks(customer, product, [3], soh=1, site=pinned_label)
    world.db.flush()
    drop_pin(
        world.db, tenant_id=world.tenant, customer_id=customer.id, site_label=pinned_label,
        latitude=5.0, longitude=6.0, actor="steward-test",
    )
    before = _count_locations(world)
    out = confirm_pins(
        world.db,
        tenant_id=world.tenant,
        items=[
            {"customer_id": customer.id, "site_label": nothing},
            {"customer_id": customer.id, "site_label": pinned_label},
            {"customer_id": customer.id, "site_label": "NO SUCH STORE"},
            {"customer_id": customer.id, "site_label": nothing, "latitude": 95.0, "longitude": 1.0},
            {"customer_id": customer.id, "site_label": nothing, "latitude": 1.0},
        ],
        actor="steward-test",
    )
    assert out["saved"] == []
    assert len(out["failed"]) == 5
    assert _count_locations(world) == before
    # a customer from another tenant is refused, not written
    other = confirm_pins(
        world.db,
        tenant_id="another-tenant",
        items=[{"customer_id": customer.id, "site_label": nothing, "latitude": 1.0, "longitude": 1.0}],
        actor="steward-test",
    )
    assert other["saved"] == [] and other["failed"][0]["error"] == "Customer not found"
    assert _count_locations(world) == before


def test_bulk_confirm_saves_the_good_items_and_reports_the_rest(world: World):
    _country(world)
    place = _suggesting_place()
    first = world.customer("SDC-C1")
    second = world.customer("SDC-C2")
    product = world.product()
    first_labels = [_chain_label(first, place, "MALL"), _chain_label(first, place, "MAIN STORE")]
    second_label = _chain_label(second, place, "CENTRE")
    skipped = f"{first.name} HEAD OFFICE WHOLESALE"
    for label in (*first_labels, skipped):
        world.weeks(first, product, [1], soh=1, site=label)
    world.weeks(second, product, [1], soh=1, site=second_label)
    world.db.flush()
    before = _count_locations(world)
    out = confirm_pins(
        world.db,
        tenant_id=world.tenant,
        items=[
            {"customer_id": first.id, "site_label": first_labels[0]},
            {"customer_id": first.id, "site_label": first_labels[1]},
            {"customer_id": second.id, "site_label": second_label},
            {"customer_id": first.id, "site_label": skipped},
        ],
        actor="steward-test",
    )
    assert len(out["saved"]) == 3
    assert [item["site_label"] for item in out["failed"]] == [skipped]
    assert _count_locations(world) == before + 3
    unpinned = [row for row in build_store_map(world.db, world.tenant)["stores"] if not row["pinned"]]
    assert [row["site_label"] for row in unpinned] == [skipped]
    too_many = [{"customer_id": first.id, "site_label": "x"}] * 501
    with pytest.raises(ValueError):
        confirm_pins(world.db, tenant_id=world.tenant, items=too_many, actor="steward-test")


def test_proposals_follow_the_tenant_country_setting_opus_r05(world: World):
    """No country, or a country without a bundled places file, proposes nothing (manual)."""
    customer = world.customer("SDC-C")
    product = world.product()
    place = _suggesting_place()
    world.weeks(customer, product, [2], soh=2, site=f"{world.code('SDC-BRANCH')} - {place['name']}")
    world.db.flush()
    def proposal():
        return build_store_map(world.db, world.tenant, [customer.id])["stores"][0]["location_suggestion"]

    unset = proposal()
    assert unset["outcome"] == "manual" and unset["reason"] == "no_gazetteer_for_country"
    _country(world, "QQ")
    other = proposal()
    assert other["reason"] == "no_gazetteer_for_country"
    _country(world, "ZA")
    za = proposal()
    assert za["outcome"] == "suggest" and za["place"] == place["name"]
    assert place_table_for_country(None) is None and place_table_for_country("za ") is _ZA


def test_store_map_and_board_customers_default_to_reporting_only_when_asked(world: World):
    reporting = world.customer("SDC-REP")
    other = world.customer("SDC-OTH")
    product = world.product()
    site = world.code("SDC-STORE")
    world.weeks(reporting, product, [4], soh=2, site=site)
    world.weeks(other, product, [3], soh=2, site=site)
    cfg = world.db.execute(
        select(CustomerReportConfig).where(CustomerReportConfig.customer_id == reporting.id)
    ).scalar_one()
    cfg.reports_expected = True
    world.db.flush()
    full_map = build_store_map(world.db, world.tenant)
    reporting_map = build_store_map(world.db, world.tenant, reporting_only=True)
    assert {store["customer_id"] for store in full_map["stores"]} == {reporting.id, other.id}
    assert {store["customer_id"] for store in reporting_map["stores"]} == {reporting.id}
    assert {c["id"] for c in full_map["customers"]} == {reporting.id, other.id}
    assert {c["id"] for c in reporting_map["customers"]} == {reporting.id}
    board_all = {c["id"] for c in list_board_customers(world.db, world.tenant)}
    board_reporting = {c["id"] for c in list_board_customers(world.db, world.tenant, reporting_only=True)}
    assert board_all == {reporting.id, other.id}
    assert board_reporting == {reporting.id}