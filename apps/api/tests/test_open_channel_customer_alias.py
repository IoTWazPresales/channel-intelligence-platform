"""Open Channel alias canonicalization."""
from app.services.commercial_planner.open_channel_customer import canonical_open_channel_customer_id


def test_alias_maps_to_canonical():
    assert (
        canonical_open_channel_customer_id(
            19, canonical_id=1, alias_ids=frozenset({1, 19})
        )
        == 1
    )


def test_non_alias_unchanged():
    assert (
        canonical_open_channel_customer_id(
            5, canonical_id=1, alias_ids=frozenset({1, 19})
        )
        == 5
    )
