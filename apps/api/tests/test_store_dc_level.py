"""Unit 1: level and owner on a location that already exists."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.store_dc.level import set_site_level
from app.services.store_dc.rules import SiteLevelRejected
from tests.store_dc_fixture import World

pytest_plugins = ("tests.store_dc_fixture",)


def test_steward_can_set_a_customer_location_level(world: World):
    customer = world.customer("SDC-C")
    from app.models.dimensions import CustomerLocation

    before = world.counts()[2]
    row = CustomerLocation(
        customer_id=customer.id,
        location_code=world.code("SDC-LOC"),
        location_name=world.code("SDC-LOC"),
        location_type="warehouse",
    )
    world.db.add(row)
    world.db.flush()
    payload = set_site_level(
        world.db,
        owner_table="customer",
        location_id=row.id,
        site_level="customer_dc",
        site_owner=None,
        actor="steward-test",
    )
    assert payload["site_level"] == "customer_dc"
    assert payload["site_owner"] == "customer"
    assert payload["confirmed_by"] == "steward-test"
    assert world.counts()[2] == before + 1


def test_service_rejects_distributor_owner_as_customer_dc(world: World):
    before = world.counts()[2]
    distributor = world.distributor()
    row = world.distributor_location(distributor, "SDC-WH")
    with pytest.raises(SiteLevelRejected):
        set_site_level(
            world.db,
            owner_table="distributor",
            location_id=row.id,
            site_level="customer_dc",
            site_owner="distributor",
            actor="steward-test",
        )
    world.db.refresh(row)
    assert row.site_level is None
    assert world.counts()[2] == before


def test_database_rejects_distributor_owner_as_customer_dc(world: World):
    distributor = world.distributor()
    row = world.distributor_location(distributor, "SDC-WH")
    row.site_level = "customer_dc"
    row.site_owner = "distributor"
    with pytest.raises(IntegrityError):
        world.db.flush()
    world.db.rollback()
