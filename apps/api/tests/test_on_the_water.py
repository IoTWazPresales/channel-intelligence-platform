"""On the water: the rules, grouping, position, slip, value and filters (pure, no database)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.commercial_tenant_profile import _normalize_on_the_water
from app.services.shipping.on_the_water import (
    DEFAULT_LANE,
    LANES,
    WaterConfig,
    WaterLine,
    build_payload,
    build_vessels,
    classify,
    config_from_overrides,
    lane_for,
    point_along,
    project_pct,
    route_to_port,
    vessel_filter_parts,
)

AS_OF = date(2026, 10, 28)
CFG = WaterConfig()


def _ln(i: int, **kw) -> WaterLine:
    base = dict(
        id=i, quantity=10, amount=100.0, currency="USD", line_state="shipped", ship_way="SEA", on_board=date(2026, 9, 19),
        port_eta=date(2026, 11, 5), forwarder="COSCO", hub="ckg", deliver_port="ZAJNB", model="P1503", distributor="Rectron",
    )
    base.update(kw)
    return WaterLine(**base)


def _payload(lines, **kw):
    args = dict(as_of=AS_OF, report_date=date(2026, 10, 27), reports={"count": 4, "earlier": 3, "since": "2026-09-29"},
                port_conditions=[], needs_look_lines=[], cfg=CFG)
    args.update(kw)
    return build_payload(lines, **args)


def test_the_four_states():
    assert classify(_ln(1), AS_OF) == "at_sea"
    assert classify(_ln(2, on_board=date(2026, 11, 2), line_state="open_order"), AS_OF) == "booked"
    assert classify(_ln(3, on_board=date(2026, 11, 2)), AS_OF) == "booked"  # shipped state with a future on-board date
    assert classify(_ln(4, port_ata=date(2026, 10, 25)), AS_OF) == "arrived"
    assert classify(_ln(5, port_ata=date(2026, 10, 25), pod=date(2026, 10, 27)), AS_OF) is None  # delivered
    assert classify(_ln(6, on_board=date(2026, 10, 28)), AS_OF) == "at_sea"  # on board today is on board
    assert classify(_ln(7, line_state="open_order"), AS_OF) is None  # open and already on board: not at sea
    assert classify(_ln(8, on_board=None), AS_OF) is None
    assert classify(_ln(9, line_state="closed_shipped"), AS_OF) is None


def test_only_sea_is_drawn_and_air_is_counted_in_the_sub_line():
    p = _payload([_ln(1), _ln(2, ship_way="AIR", quantity=7), _ln(3, ship_way="TRUCK/SEA", quantity=5), _ln(4, ship_way="EXPRESS", quantity=2)])
    assert p["tiles"]["at_sea"]["units"] == 15  # SEA and TRUCK/SEA
    assert p["tiles"]["at_sea"]["air_units"] == 9  # AIR and EXPRESS
    assert sum(v["units"] for v in p["vessels"]) == 15


def test_lines_with_the_same_on_board_date_eta_port_and_lane_are_one_vessel():
    p = _payload([_ln(1), _ln(2, quantity=5, hub="szx"), _ln(3, port_eta=date(2026, 11, 8))])
    assert len(p["vessels"]) == 2
    big = max(p["vessels"], key=lambda v: v["units"])
    assert (big["units"], big["lines"], big["inferred"]) == (15, 2, True)
    assert big["lane_label"] == "Chongqing / Shenzhen → Durban → City Deep"
    assert big["key"].startswith("i:2026-09-19|2026-11-05|ZAJNB|asia_durban")


def test_a_named_vessel_groups_by_name_and_voyage():
    p = _payload([_ln(1, vessel_name="MSC Anna", voyage_no="V9"), _ln(2, vessel_name="msc anna ", voyage_no="v9", port_eta=date(2026, 11, 9)), _ln(3)])
    named = [v for v in p["vessels"] if not v["inferred"]]
    assert len(named) == 1 and named[0]["lines"] == 2 and named[0]["key"] == "n:msc anna|v9"


def test_position_is_the_share_of_on_board_to_eta_elapsed_along_the_lane():
    # 18 Sep to 7 Nov is 50 days; 18 Sep to 28 Oct (as of) is 40 of them, so 80 %.
    v = build_vessels([_ln(1, on_board=date(2026, 9, 18), port_eta=date(2026, 11, 7))], as_of=AS_OF, report_date=None, cfg=CFG)[0]
    assert v["pct"] == 80.0
    lon, lat = point_along(LANES[DEFAULT_LANE], 0.8)
    x, y = project_pct(lon, lat)
    assert (v["x"], v["y"]) == (round(x, 2), round(y, 2))
    # Halfway and the ends
    mid = build_vessels([_ln(1, on_board=date(2026, 10, 18), port_eta=date(2026, 11, 7))], as_of=AS_OF, report_date=None, cfg=CFG)[0]
    assert mid["pct"] == 50.0
    assert point_along(LANES[DEFAULT_LANE], 0) == LANES[DEFAULT_LANE][0]
    assert point_along(LANES[DEFAULT_LANE], 1) == LANES[DEFAULT_LANE][-1]


def test_overdue_arrival_is_drawn_at_the_discharge_port():
    v = build_vessels([_ln(1, on_board=date(2026, 9, 1), port_eta=date(2026, 10, 20), deliver_port="ZADUR", hub="c")], as_of=AS_OF, report_date=None, cfg=CFG)[0]
    assert v["overdue"] is True and v["days_overdue"] == 8
    assert (v["x"], v["y"]) == (33.54, 86.18)  # Durban
    p = _payload([_ln(1, port_eta=date(2026, 10, 20))])
    assert p["tiles"]["at_sea"]["overdue_vessels"] == 1


def test_port_louis_is_drawn_at_port_louis_and_city_deep_at_durban():
    route, known = route_to_port("asia_durban", "MUPLU")
    assert known and route[-1] == (57.5, -20.16)
    assert route_to_port("asia_durban", "ZAJNB")[0] == LANES["asia_durban"]
    assert route_to_port("asia_durban", "XXXXX")[1] is False


def test_unknown_hub_uses_the_default_lane_and_says_the_route_is_assumed():
    assert lane_for("ckg", CFG) == ("asia_durban", False)
    assert lane_for("nl", CFG) == ("europe_durban", False)
    assert lane_for("zz", CFG) == (DEFAULT_LANE, True)
    v = _payload([_ln(1, hub="y")])["vessels"][0]
    assert v["route_assumed"] is True and v["lane_id"] == DEFAULT_LANE


def test_value_is_per_currency_never_summed_and_suspect_amounts_are_left_out():
    p = _payload([_ln(1, amount=100, currency="USD"), _ln(2, amount=40, currency="USD"), _ln(3, amount=70, currency="EUR", hub="nl"), _ln(4, amount=9e9, amount_suspect=True)])
    assert p["tiles"]["at_sea"]["amount"] == [{"currency": "EUR", "amount": 70.0}, {"currency": "USD", "amount": 140.0}]
    usd_only = _payload([_ln(1), _ln(2)])["tiles"]["at_sea"]["amount"]
    assert usd_only == [{"currency": "USD", "amount": 200.0}]


def test_arrived_not_delivered_is_split_by_discharge_port():
    p = _payload([_ln(1, port_ata=date(2026, 10, 25), deliver_port="ZAJNB", quantity=30), _ln(2, port_ata=date(2026, 10, 26), deliver_port="MUPLU", quantity=5),
                  _ln(3, port_ata=date(2026, 10, 26), deliver_port="ZAJNB", quantity=20)])
    t = p["tiles"]["arrived"]
    assert t["units"] == 55 and t["lines"] == 3
    assert t["by_port"] == [{"name": "City Deep", "units": 50}, {"name": "Port Louis", "units": 5}]
    rows = {r["code"]: r["waiting_units"] for r in p["port_rows"]}
    assert rows["ZAJNB"] == 50 and rows["MUPLU"] == 5


def test_booked_not_on_board():
    p = _payload([_ln(1, on_board=date(2026, 11, 2), line_state="open_order", quantity=12), _ln(2, on_board=date(2026, 11, 9), quantity=3)])
    assert p["tiles"]["booked"] == {"units": 15, "lines": 2}


def test_slip_is_current_eta_against_the_first_report_and_the_vessel_takes_the_largest():
    a = _ln(1, first_eta=date(2026, 10, 22), first_eta_report=date(2026, 9, 29))
    b = _ln(2, first_eta=date(2026, 10, 30), first_eta_report=date(2026, 9, 29))
    p = _payload([a, b])
    (v,) = p["vessels"]
    assert v["slip_days"] == 14  # 5 Nov against 22 Oct, not against 30 Oct
    assert v["history"] == {"first_eta": "2026-10-22", "first_report": "2026-09-29", "current_eta": "2026-11-05", "latest_report": "2026-10-27"}
    assert p["tiles"]["eta_moved"] == {"vessels_moved": 1, "vessels": 1, "min_days": 14, "max_days": 14, "since": "2026-09-29"}


def test_no_history_or_an_unmoved_eta_is_on_time():
    on_time = _payload([_ln(1, first_eta=date(2026, 11, 5), first_eta_report=date(2026, 9, 29))])["vessels"][0]
    assert on_time["slip_days"] == 0
    assert _payload([_ln(1)])["vessels"][0]["slip_days"] == 0
    # An ETA that came earlier is not a slip.
    assert _payload([_ln(1, first_eta=date(2026, 11, 12), first_eta_report=date(2026, 9, 29))])["vessels"][0]["slip_days"] == 0


def test_distributors_and_top_four_products_with_the_rest_counted():
    lines = [_ln(i, model=f"M{i}", quantity=100 - i, distributor="A" if i % 2 else "B") for i in range(1, 8)]
    v = _payload(lines)["vessels"][0]
    assert [p["name"] for p in v["products"]] == ["M1", "M2", "M3", "M4"]
    assert v["more_models"] == 3
    assert {d["name"] for d in v["distributors"]} == {"A", "B"}


def test_the_report_is_stale_only_past_the_tenant_threshold():
    fresh = _payload([_ln(1)], report_date=date(2026, 10, 21))
    assert fresh["report_stale"] is False and fresh["report_age_days"] == 7
    assert _payload([_ln(1)], report_date=date(2026, 10, 20))["report_stale"] is True
    custom = _payload([_ln(1)], report_date=date(2026, 10, 20), cfg=config_from_overrides({"stale_report_days": 10}))
    assert custom["report_stale"] is False


def test_needs_a_look_counts_lines_units_and_the_distributor_split():
    stuck = [
        WaterLine(id=1, quantity=500, line_state="open_order", distributor="Pepkor", on_board=date(2026, 10, 18), first_on_board=date(2026, 10, 11), first_seen_report=date(2026, 9, 29)),
        WaterLine(id=2, quantity=100, line_state="open_order", distributor="DCC", on_board=date(2026, 10, 18), first_on_board=date(2026, 10, 18)),
    ]
    n = _payload([], needs_look_lines=stuck)["needs_look"]
    assert (n["lines"], n["units"]) == (2, 600)
    assert n["distributors"][0] == {"name": "Pepkor", "units": 500}
    assert n["since"] == "2026-09-29" and n["on_board_moved"] == {"from": "2026-10-11", "to": "2026-10-18"}
    assert _payload([], needs_look_lines=[])["needs_look"] is None


def test_a_vessel_key_round_trips_to_a_filter():
    v = _payload([_ln(1)])["vessels"][0]
    parts = vessel_filter_parts(v["key"], CFG)
    assert parts["on_board"] == date(2026, 9, 19) and parts["port_eta"] == date(2026, 11, 5)
    assert parts["deliver_port"] == "ZAJNB" and "ckg" in parts["hubs"] and parts["include_unknown_hubs"] is True
    assert vessel_filter_parts("n:msc anna|v9", CFG) == {"vessel_name": "msc anna", "voyage_no": "v9"}
    assert vessel_filter_parts("garbage", CFG) is None and vessel_filter_parts("i:x|y", CFG) is None


def test_tenant_override_is_validated():
    assert _normalize_on_the_water({"hub_lane": {"YY": "europe_durban"}, "needs_look_days": 10}, strict=True) == {"hub_lane": {"yy": "europe_durban"}, "needs_look_days": 10}
    with pytest.raises(ValueError, match="sea lane|one of"):
        _normalize_on_the_water({"hub_lane": {"yy": "moon"}}, strict=True)
    with pytest.raises(ValueError, match="days"):
        _normalize_on_the_water({"stale_report_days": 0}, strict=True)
    assert _normalize_on_the_water({"stale_report_days": 0, "needs_look_days": 5}, strict=False) == {"needs_look_days": 5}
    cfg = config_from_overrides({"hub_lane": {"yy": "europe_durban"}})
    assert lane_for("yy", cfg) == ("europe_durban", False)


def test_port_markers_carry_a_label_side_only_where_the_map_config_sets_one() -> None:
    from app.services.shipping.on_the_water import PORT_LABEL_SIDE, port_markers

    by_id = {m["id"]: m for m in port_markers()}
    assert PORT_LABEL_SIDE == {"CHONGQING": "left"}
    assert by_id["CHONGQING"]["label_side"] == "left"
    assert all("label_side" not in m for k, m in by_id.items() if k != "CHONGQING")
