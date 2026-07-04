"""Plan-scoped lineup entity resolution aggregation (unit tests, no cip writes)."""

from types import SimpleNamespace

from app.services.commercial_planner.lineup_entity_resolution import (
    _accumulate_line_entity_tokens,
    _line_matches_distributor_token,
    normalize_entity_token,
    open_channel_distributor_hint_from_line,
)


def test_open_channel_route_hint_surfaces_for_unresolved_distributor():
    ln = SimpleNamespace(
        id=1,
        case_id=90,
        customer_id=None,
        customer_token=None,
        distributor_id=None,
        raw_row_payload={
            "staging_open_channel": True,
            "channel_route_uploaded_cell": "Channel - UnknownDisti",
        },
    )
    assert open_channel_distributor_hint_from_line(ln) == "UnknownDisti"  # type: ignore[arg-type]
    assert _line_matches_distributor_token(ln, normalize_entity_token("UnknownDisti"))  # type: ignore[arg-type]


def test_plan_token_accumulation_dedupes_across_cases():
    customer_map: dict = {}
    distributor_map: dict = {}
    ln1 = SimpleNamespace(
        id=1,
        customer_token="MITSUMI",
        customer_id=None,
        distributor_id=1,
        raw_row_payload={},
    )
    ln2 = SimpleNamespace(
        id=2,
        customer_token="MITSUMI",
        customer_id=None,
        distributor_id=1,
        raw_row_payload={},
    )
    _accumulate_line_entity_tokens(ln1, 7, customer_map=customer_map, distributor_map=distributor_map, sample_ids_per_token=5)  # type: ignore[arg-type]
    _accumulate_line_entity_tokens(ln2, 16, customer_map=customer_map, distributor_map=distributor_map, sample_ids_per_token=5)  # type: ignore[arg-type]
    assert len(customer_map) == 1
    entry = customer_map["mitsumi"]
    assert entry["line_count"] == 2
    assert entry["case_ids"] == {7, 16}
